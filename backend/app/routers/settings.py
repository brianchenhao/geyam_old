from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import Principal, get_session, require_role
from app.models import TenantSettings
from app.services import audit, crypto

router = APIRouter(prefix="/settings", tags=["settings"])

UPLOADS_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"
ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB


class SettingsOut(BaseModel):
    tenant_id: int
    billplz_mode: str
    billplz_api_key_set: bool
    billplz_collection_id: str | None
    billplz_xsign_key_set: bool
    logo_path: str | None
    receipt_footer: str
    shop_contact_email: str | None
    shop_contact_phone: str | None
    yolo_conf_threshold: float
    yolo_conf_minimum: float
    openai_daily_limit: int


class SettingsPatch(BaseModel):
    billplz_api_key: str | None = Field(default=None, min_length=1)
    billplz_collection_id: str | None = None
    billplz_xsign_key: str | None = Field(default=None, min_length=1)
    billplz_mode: str | None = Field(default=None, pattern=r"^(sandbox|production)$")
    receipt_footer: str | None = None
    shop_contact_email: EmailStr | None = None
    shop_contact_phone: str | None = Field(default=None, max_length=30)


async def _load(session: AsyncSession, tenant_id: int) -> TenantSettings:
    s = await session.get(TenantSettings, tenant_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "settings missing for tenant")
    return s


def _to_out(s: TenantSettings) -> SettingsOut:
    return SettingsOut(
        tenant_id=s.tenant_id,
        billplz_mode=s.billplz_mode,
        billplz_api_key_set=bool(s.billplz_api_key),
        billplz_collection_id=s.billplz_collection_id,
        billplz_xsign_key_set=bool(s.billplz_xsign_key),
        logo_path=s.logo_path,
        receipt_footer=s.receipt_footer,
        shop_contact_email=s.shop_contact_email,
        shop_contact_phone=s.shop_contact_phone,
        yolo_conf_threshold=float(s.yolo_conf_threshold),
        yolo_conf_minimum=float(s.yolo_conf_minimum),
        openai_daily_limit=s.openai_daily_limit,
    )


@router.get("", response_model=SettingsOut)
async def get_settings(
    p: Principal = Depends(require_role("owner", "cashier")),
    session: AsyncSession = Depends(get_session),
):
    return _to_out(await _load(session, p.tenant_id))


@router.patch("", response_model=SettingsOut)
async def patch_settings(
    body: SettingsPatch,
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    s = await _load(session, p.tenant_id)
    changed: dict[str, object] = {}

    if body.billplz_api_key is not None:
        s.billplz_api_key = crypto.encrypt(body.billplz_api_key)
        changed["billplz_api_key"] = "<set>"
    if body.billplz_xsign_key is not None:
        s.billplz_xsign_key = crypto.encrypt(body.billplz_xsign_key)
        changed["billplz_xsign_key"] = "<set>"
    for field in ("billplz_collection_id", "billplz_mode", "receipt_footer",
                  "shop_contact_phone"):
        val = getattr(body, field)
        if val is not None:
            setattr(s, field, val)
            changed[field] = val
    if body.shop_contact_email is not None:
        s.shop_contact_email = str(body.shop_contact_email)
        changed["shop_contact_email"] = s.shop_contact_email

    if changed:
        await audit.write(
            session, tenant_id=p.tenant_id, user_id=p.user_id,
            action="settings.update", entity="tenant_settings",
            entity_id=p.tenant_id, meta={"fields": list(changed.keys())},
        )
    await session.commit()
    return _to_out(s)


@router.post("/logo", response_model=SettingsOut)
async def upload_logo(
    file: UploadFile = File(...),
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    if file.content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "png/jpeg/webp only")
    data = await file.read()
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "logo > 2MB")
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[file.content_type]
    tenant_dir = UPLOADS_ROOT / str(p.tenant_id)
    tenant_dir.mkdir(parents=True, exist_ok=True)
    dest = tenant_dir / f"logo.{ext}"
    dest.write_bytes(data)
    rel = f"/uploads/{p.tenant_id}/logo.{ext}"

    s = await _load(session, p.tenant_id)
    s.logo_path = rel
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="settings.logo_upload", entity="tenant_settings",
        entity_id=p.tenant_id, meta={"path": rel, "bytes": len(data)},
    )
    await session.commit()
    return _to_out(s)


class BillplzCredReveal(BaseModel):
    billplz_api_key: str | None
    billplz_xsign_key: str | None


@router.get("/billplz/_internal", response_model=BillplzCredReveal,
            include_in_schema=False)
async def reveal_billplz_creds(
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    """Owner-only decrypt roundtrip, used for dev verification.
    Production code paths call crypto.decrypt() directly in the Billplz service."""
    s = await _load(session, p.tenant_id)
    return BillplzCredReveal(
        billplz_api_key=crypto.decrypt(s.billplz_api_key),
        billplz_xsign_key=crypto.decrypt(s.billplz_xsign_key),
    )
