import csv
import io
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import Principal, get_session, require_role
from app.models import MenuItem, TrainingJob
from app.services import audit
from app.services.video import extract_middle_frame, probe_duration_sec

router = APIRouter(prefix="/menu", tags=["menu"])

UPLOADS_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"
ALLOWED_IMG = {"image/png", "image/jpeg", "image/webp"}
ALLOWED_VIDEO = {"video/mp4", "video/quicktime", "video/x-matroska"}
MAX_IMG_BYTES = 5 * 1024 * 1024
MAX_VIDEO_BYTES = 100 * 1024 * 1024  # plan: ≤100 MB


class MenuItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(gt=0)
    category: str | None = None
    barcode: str | None = Field(default=None, max_length=64)
    stock_qty: int = Field(default=0, ge=0)
    reorder_point: int = Field(default=5, ge=0)


class MenuItemPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    price: Decimal | None = Field(default=None, gt=0)
    category: str | None = None
    barcode: str | None = Field(default=None, max_length=64)
    stock_qty: int | None = Field(default=None, ge=0)
    reorder_point: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class MenuItemOut(BaseModel):
    id: int
    name: str
    label: str
    price: Decimal
    category: str | None
    barcode: str | None
    stock_qty: int
    reorder_point: int
    avg_cost: Decimal
    image_path: str | None
    is_active: bool
    frame_count: int

    model_config = {"from_attributes": True}


class TrainingJobOut(BaseModel):
    id: int
    menu_item_id: int | None
    status: str
    video_path: str
    frames_extracted: int

    model_config = {"from_attributes": True}


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "item"


async def _unique_label(session: AsyncSession, tenant_id: int, name: str) -> str:
    base = _slugify(name)
    label = base
    n = 2
    while await session.scalar(
        select(MenuItem.id).where(MenuItem.label == label)
    ):
        label = f"{base}_{n}"
        n += 1
    return label


@router.get("", response_model=list[MenuItemOut])
async def list_menu(
    p: Principal = Depends(require_role("owner", "cashier")),
    session: AsyncSession = Depends(get_session),
):
    rows = await session.scalars(select(MenuItem).order_by(MenuItem.name))
    return list(rows)


@router.post("", response_model=MenuItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: MenuItemIn,
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    label = await _unique_label(session, p.tenant_id, body.name)
    item = MenuItem(
        tenant_id=p.tenant_id,
        name=body.name,
        label=label,
        price=body.price,
        category=body.category,
        barcode=body.barcode,
        stock_qty=body.stock_qty,
        reorder_point=body.reorder_point,
    )
    session.add(item)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "duplicate name")
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="menu.create", entity="menu_item", entity_id=item.id,
        meta={"name": item.name},
    )
    await session.commit()
    return item


@router.get("/{item_id}", response_model=MenuItemOut)
async def get_item(
    item_id: int,
    p: Principal = Depends(require_role("owner", "cashier")),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(MenuItem, item_id)
    if item is None or item.tenant_id != p.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return item


@router.patch("/{item_id}", response_model=MenuItemOut)
async def patch_item(
    item_id: int,
    body: MenuItemPatch,
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(MenuItem, item_id)
    if item is None or item.tenant_id != p.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    changed: dict[str, object] = {}
    for field in ("name", "price", "category", "barcode", "stock_qty",
                  "reorder_point", "is_active"):
        val = getattr(body, field)
        if val is not None:
            setattr(item, field, val)
            changed[field] = str(val) if field == "price" else val
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "duplicate name")
    if changed:
        await audit.write(
            session, tenant_id=p.tenant_id, user_id=p.user_id,
            action="menu.update", entity="menu_item", entity_id=item.id,
            meta={"fields": list(changed.keys())},
        )
    await session.commit()
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(MenuItem, item_id)
    if item is None or item.tenant_id != p.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    await session.delete(item)
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="menu.delete", entity="menu_item", entity_id=item_id,
    )
    await session.commit()
    return None


class BulkResult(BaseModel):
    inserted: int
    updated: int
    skipped: int
    errors: list[str]


@router.post("/bulk", response_model=BulkResult)
async def bulk_upsert(
    file: UploadFile = File(...),
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    """CSV columns: name,price,category,barcode,stock_qty,reorder_point (category onward optional).
    Upsert key is (tenant_id, name)."""
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    inserted = updated = skipped = 0
    errors: list[str] = []

    for i, row in enumerate(reader, start=2):  # row 1 is header
        name = (row.get("name") or "").strip()
        raw_price = (row.get("price") or "").strip()
        if not name or not raw_price:
            errors.append(f"row {i}: missing name/price")
            skipped += 1
            continue
        try:
            price = Decimal(raw_price)
            if price <= 0:
                raise InvalidOperation()
        except InvalidOperation:
            errors.append(f"row {i}: bad price '{raw_price}'")
            skipped += 1
            continue
        stock = int(row.get("stock_qty") or 0)
        reorder = int(row.get("reorder_point") or 5)
        category = (row.get("category") or None) or None
        barcode = (row.get("barcode") or None) or None

        existing = await session.scalar(select(MenuItem).where(MenuItem.name == name))
        if existing:
            existing.price = price
            existing.category = category or existing.category
            existing.barcode = barcode or existing.barcode
            existing.stock_qty = stock
            existing.reorder_point = reorder
            updated += 1
        else:
            label = await _unique_label(session, p.tenant_id, name)
            session.add(
                MenuItem(
                    tenant_id=p.tenant_id, name=name, label=label, price=price,
                    category=category, barcode=barcode, stock_qty=stock,
                    reorder_point=reorder,
                )
            )
            inserted += 1

    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="menu.bulk_upsert", entity="menu_item",
        meta={"inserted": inserted, "updated": updated, "skipped": skipped},
    )
    await session.commit()
    return BulkResult(inserted=inserted, updated=updated, skipped=skipped, errors=errors)


@router.post("/{item_id}/image", response_model=MenuItemOut)
async def upload_image(
    item_id: int,
    file: UploadFile = File(...),
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    if file.content_type not in ALLOWED_IMG:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "png/jpeg/webp only")
    data = await file.read()
    if len(data) > MAX_IMG_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "image > 5MB")

    item = await session.get(MenuItem, item_id)
    if item is None or item.tenant_id != p.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")

    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[file.content_type]
    dest_dir = UPLOADS_ROOT / str(p.tenant_id) / "products"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{item.id}.{ext}"
    dest.write_bytes(data)
    item.image_path = f"/uploads/{p.tenant_id}/products/{item.id}.{ext}"
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="menu.image_upload", entity="menu_item", entity_id=item.id,
        meta={"path": item.image_path, "bytes": len(data)},
    )
    await session.commit()
    return item


@router.post("/{item_id}/video", response_model=TrainingJobOut, status_code=status.HTTP_201_CREATED)
async def upload_video(
    item_id: int,
    file: UploadFile = File(...),
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    if file.content_type not in ALLOWED_VIDEO:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "mp4/mov/mkv only")
    data = await file.read()
    if len(data) > MAX_VIDEO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "video > 100MB")

    item = await session.get(MenuItem, item_id)
    if item is None or item.tenant_id != p.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")

    videos_dir = UPLOADS_ROOT / str(p.tenant_id) / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    ext = (Path(file.filename or "").suffix or ".mp4").lower()
    video_path = videos_dir / f"{item.id}{ext}"
    video_path.write_bytes(data)

    dur = probe_duration_sec(str(video_path))
    if dur is not None and dur > 30.0:
        video_path.unlink(missing_ok=True)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"video longer than 30s ({dur:.1f}s)",
        )

    # Middle-frame extraction (Phase 6 will enqueue a real training job on top of this).
    frame_dir = UPLOADS_ROOT / str(p.tenant_id) / "products"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_path = frame_dir / f"{item.id}.jpg"
    try:
        extract_middle_frame(str(video_path), str(frame_path))
        item.image_path = f"/uploads/{p.tenant_id}/products/{item.id}.jpg"
    except Exception as e:
        # Don't fail the upload — the training job still captures the video.
        # The image can be set later via /menu/{id}/image.
        errmsg = f"middle-frame failed: {e}"
    else:
        errmsg = None

    job = TrainingJob(
        tenant_id=p.tenant_id,
        menu_item_id=item.id,
        video_path=f"/uploads/{p.tenant_id}/videos/{item.id}{ext}",
        status="queued",
        error=errmsg,
    )
    session.add(job)
    await session.flush()
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="training.video_upload", entity="training_job", entity_id=job.id,
        meta={"menu_item_id": item.id, "bytes": len(data)},
    )
    await session.commit()
    return job
