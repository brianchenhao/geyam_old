"""Phase 5 — Menu CRUD, CSV bulk upsert, product image upload."""
import csv
import io
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, constr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import UPLOADS_DIR
from app.deps import get_current_user, get_session, get_tenant, require_role
from app.models.menu_item import MenuItem
from app.services.audit import audit
from app.services.chenki_menu_ask import ask_menu
from app.services.plan_enforcement import ensure_active, ensure_item_quota, load_tenant

router = APIRouter(prefix="/menu", tags=["menu"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}

_label_bad_chars = re.compile(r"[^a-z0-9_-]+")


def _make_label(name: str) -> str:
    s = name.strip().lower().replace(" ", "_")
    s = _label_bad_chars.sub("", s)
    return s[:80] or "item"


class MenuItemOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    label: str
    price: Decimal
    category: Optional[str] = None
    barcode: Optional[str] = None
    stock_qty: int
    reorder_point: int
    image_path: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


class MenuItemCreateIn(BaseModel):
    name: constr(strip_whitespace=True, min_length=1, max_length=100)
    price: Decimal = Field(ge=0)
    category: Optional[constr(max_length=50)] = None
    barcode: Optional[constr(max_length=64)] = None
    stock_qty: int = Field(default=0, ge=0)
    reorder_point: int = Field(default=5, ge=0)


class MenuItemPatchIn(BaseModel):
    name: Optional[constr(strip_whitespace=True, min_length=1, max_length=100)] = None
    price: Optional[Decimal] = Field(default=None, ge=0)
    category: Optional[constr(max_length=50)] = None
    barcode: Optional[constr(max_length=64)] = None
    stock_qty: Optional[int] = Field(default=None, ge=0)
    reorder_point: Optional[int] = Field(default=None, ge=0)


class BulkResult(BaseModel):
    inserted: int
    updated: int
    errors: list[str]


class MenuAskIn(BaseModel):
    question: constr(strip_whitespace=True, min_length=1, max_length=500)


class MenuAskOut(BaseModel):
    answer: str


@router.post("/ask")
async def menu_ask(body: MenuAskIn,
                   tenant_id: int = Depends(get_tenant),
                   session: AsyncSession = Depends(get_session)) -> MenuAskOut:
    """Free-form Q&A over this tenant's active menu, answered by chenki-llm.

    Cashier-facing: any authenticated user with a tenant context can ask.
    Menu is loaded fresh per call so a tenant never sees another's items.
    """
    res = await session.execute(
        select(MenuItem).where(MenuItem.is_active.is_(True)).order_by(MenuItem.name)
    )
    menu = [
        {"name": m.name, "category": m.category, "price": str(m.price)}
        for m in res.scalars().all()
    ]
    answer = await ask_menu(body.question, menu)
    return MenuAskOut(answer=answer)


@router.get("")
async def list_menu(include_archived: bool = False,
                    tenant_id: int = Depends(get_tenant),
                    session: AsyncSession = Depends(get_session)) -> list[MenuItemOut]:
    stmt = select(MenuItem).order_by(MenuItem.name)
    if not include_archived:
        stmt = stmt.where(MenuItem.is_active.is_(True))
    res = await session.execute(stmt)
    return [MenuItemOut.model_validate(m) for m in res.scalars().all()]


@router.post("", dependencies=[Depends(require_role("owner"))])
async def create_item(body: MenuItemCreateIn,
                      user_claims: dict = Depends(get_current_user),
                      tenant_id: int = Depends(get_tenant),
                      session: AsyncSession = Depends(get_session)) -> MenuItemOut:
    tenant = await load_tenant(session, tenant_id)
    ensure_active(tenant)
    await ensure_item_quota(session, tenant)

    label = _make_label(body.name)
    clash = (await session.execute(
        select(MenuItem).where((MenuItem.name == body.name) | (MenuItem.label == label))
    )).scalars().first()
    if clash:
        raise HTTPException(status_code=409, detail="name or derived label already exists")
    item = MenuItem(
        tenant_id=tenant_id,
        name=body.name, label=label, price=body.price,
        category=body.category, barcode=body.barcode,
        stock_qty=body.stock_qty, reorder_point=body.reorder_point,
    )
    session.add(item)
    await session.flush()
    await audit(session, action="menu.create", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="menu_item", entity_id=item.id,
                meta={"name": item.name})
    await session.commit()
    await session.refresh(item)
    return MenuItemOut.model_validate(item)


@router.patch("/{item_id}", dependencies=[Depends(require_role("owner"))])
async def patch_item(item_id: int, body: MenuItemPatchIn,
                     user_claims: dict = Depends(get_current_user),
                     tenant_id: int = Depends(get_tenant),
                     session: AsyncSession = Depends(get_session)) -> MenuItemOut:
    item = (await session.execute(select(MenuItem).where(MenuItem.id == item_id))).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="item not found")
    changed: list[str] = []
    for attr in ("name", "price", "category", "barcode", "stock_qty", "reorder_point"):
        v = getattr(body, attr)
        if v is not None and getattr(item, attr) != v:
            setattr(item, attr, v)
            changed.append(attr)
    if "name" in changed:
        item.label = _make_label(item.name)
    if changed:
        await audit(session, action="menu.update", tenant_id=tenant_id,
                    user_id=user_claims.get("user_id"), entity="menu_item", entity_id=item.id,
                    meta={"fields": changed})
        await session.commit()
        await session.refresh(item)
    return MenuItemOut.model_validate(item)


@router.delete("/{item_id}", dependencies=[Depends(require_role("owner"))])
async def soft_delete_item(item_id: int,
                           user_claims: dict = Depends(get_current_user),
                           tenant_id: int = Depends(get_tenant),
                           session: AsyncSession = Depends(get_session)) -> MenuItemOut:
    item = (await session.execute(select(MenuItem).where(MenuItem.id == item_id))).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="item not found")
    item.is_active = False
    await audit(session, action="menu.delete", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="menu_item", entity_id=item.id)
    await session.commit()
    await session.refresh(item)
    return MenuItemOut.model_validate(item)


@router.post("/{item_id}/restore", dependencies=[Depends(require_role("owner"))])
async def restore_item(item_id: int,
                       user_claims: dict = Depends(get_current_user),
                       tenant_id: int = Depends(get_tenant),
                       session: AsyncSession = Depends(get_session)) -> MenuItemOut:
    item = (await session.execute(select(MenuItem).where(MenuItem.id == item_id))).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="item not found")
    item.is_active = True
    await audit(session, action="menu.restore", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="menu_item", entity_id=item.id)
    await session.commit()
    await session.refresh(item)
    return MenuItemOut.model_validate(item)


@router.post("/{item_id}/image", dependencies=[Depends(require_role("owner"))])
async def upload_item_image(item_id: int,
                             file: UploadFile = File(...),
                             user_claims: dict = Depends(get_current_user),
                             tenant_id: int = Depends(get_tenant),
                             session: AsyncSession = Depends(get_session)) -> MenuItemOut:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"content_type must be {sorted(ALLOWED_IMAGE_TYPES)}")
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=f"image max {MAX_IMAGE_BYTES} bytes")

    item = (await session.execute(select(MenuItem).where(MenuItem.id == item_id))).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="item not found")

    try:
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(data)).convert("RGB")
        img.thumbnail((1024, 1024))
        out_dir = UPLOADS_DIR / str(tenant_id) / "products"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{item.id}.jpg"
        img.save(out_path, format="JPEG", quality=90)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid image: {e}")

    item.image_path = f"/uploads/{tenant_id}/products/{item.id}.jpg"
    await audit(session, action="menu.update", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="menu_item", entity_id=item.id,
                meta={"image_uploaded": True, "bytes": len(data)})
    await session.commit()
    await session.refresh(item)
    return MenuItemOut.model_validate(item)


@router.post("/bulk", dependencies=[Depends(require_role("owner"))])
async def bulk_upsert(file: UploadFile = File(...),
                      user_claims: dict = Depends(get_current_user),
                      tenant_id: int = Depends(get_tenant),
                      session: AsyncSession = Depends(get_session)) -> BulkResult:
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="empty or unreadable CSV")

    missing = [c for c in ("name", "price") if c not in reader.fieldnames]
    if missing:
        raise HTTPException(status_code=400, detail=f"missing required columns: {missing}")

    inserted = 0
    updated = 0
    errors: list[str] = []

    def _int(v, default):
        try:
            return int(v) if v not in (None, "") else default
        except ValueError:
            return default

    for row_idx, row in enumerate(reader, start=2):
        name = (row.get("name") or "").strip()
        if not name:
            errors.append(f"row {row_idx}: missing name")
            continue
        try:
            price = Decimal((row.get("price") or "0").strip())
        except InvalidOperation:
            errors.append(f"row {row_idx} ({name}): bad price")
            continue

        values = {
            "tenant_id": tenant_id,
            "name": name,
            "label": _make_label(name),
            "price": price,
            "category": (row.get("category") or "") or None,
            "barcode": (row.get("barcode") or "") or None,
            "stock_qty": _int(row.get("stock_qty"), 0),
            "reorder_point": _int(row.get("reorder_point"), 5),
            "is_active": True,
        }

        existing = (await session.execute(
            select(MenuItem).where(MenuItem.name == name)
        )).scalars().first()

        if existing:
            for k, v in values.items():
                if k == "tenant_id":
                    continue
                setattr(existing, k, v)
            updated += 1
        else:
            session.add(MenuItem(**values))
            inserted += 1

    await audit(session, action="menu.bulk_upsert", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"),
                meta={"inserted": inserted, "updated": updated, "errors": len(errors)})
    await session.commit()
    return BulkResult(inserted=inserted, updated=updated, errors=errors)
