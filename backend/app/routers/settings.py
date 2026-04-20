"""Phase 4 — tenant settings (Billplz creds, branding, thresholds) + logo upload."""
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, EmailStr, constr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import UPLOADS_DIR
from app.deps import get_current_user, get_session, get_tenant, require_role
from app.models.tenant_settings import TenantSettings
from app.services.audit import audit
from app.services.crypto import decrypt_secret, encrypt_secret

router = APIRouter(prefix="/settings", tags=["settings"])

MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB per plan
ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/webp"}


# ------- schemas -------

class SettingsOut(BaseModel):
    tenant_id: int
    billplz_mode: Literal["sandbox", "production"]
    billplz_collection_id: Optional[str] = None
    billplz_configured: bool  # True when all 3 creds (api key, collection, xsign) are present
    logo_path: Optional[str] = None
    receipt_footer: Optional[str] = None
    shop_contact_email: Optional[str] = None
    shop_contact_phone: Optional[str] = None
    yolo_conf_threshold: float
    yolo_conf_minimum: float
    openai_daily_limit: int


class SettingsPatch(BaseModel):
    billplz_api_key: Optional[str] = None          # write-only
    billplz_collection_id: Optional[str] = None
    billplz_xsign_key: Optional[str] = None        # write-only
    billplz_mode: Optional[Literal["sandbox", "production"]] = None
    receipt_footer: Optional[constr(max_length=500)] = None
    shop_contact_email: Optional[EmailStr] = None
    shop_contact_phone: Optional[constr(max_length=30)] = None
    yolo_conf_threshold: Optional[float] = None
    yolo_conf_minimum: Optional[float] = None
    openai_daily_limit: Optional[int] = None


# ------- helpers -------

async def _get_or_create_settings(session: AsyncSession, tenant_id: int) -> TenantSettings:
    s = (await session.execute(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )).scalars().first()
    if s is None:
        s = TenantSettings(tenant_id=tenant_id)
        session.add(s)
        await session.flush()
    return s


def _to_out(s: TenantSettings) -> SettingsOut:
    billplz_ok = bool(s.billplz_api_key and s.billplz_collection_id and s.billplz_xsign_key)
    return SettingsOut(
        tenant_id=s.tenant_id,
        billplz_mode=s.billplz_mode,
        billplz_collection_id=s.billplz_collection_id,
        billplz_configured=billplz_ok,
        logo_path=s.logo_path,
        receipt_footer=s.receipt_footer,
        shop_contact_email=s.shop_contact_email,
        shop_contact_phone=s.shop_contact_phone,
        yolo_conf_threshold=s.yolo_conf_threshold,
        yolo_conf_minimum=s.yolo_conf_minimum,
        openai_daily_limit=s.openai_daily_limit,
    )


# ------- endpoints -------

@router.get("", dependencies=[Depends(require_role("owner"))])
async def get_settings(tenant_id: int = Depends(get_tenant),
                       session: AsyncSession = Depends(get_session)) -> SettingsOut:
    s = await _get_or_create_settings(session, tenant_id)
    await session.commit()
    return _to_out(s)


@router.patch("", dependencies=[Depends(require_role("owner"))])
async def patch_settings(body: SettingsPatch,
                         user_claims: dict = Depends(get_current_user),
                         tenant_id: int = Depends(get_tenant),
                         session: AsyncSession = Depends(get_session)) -> SettingsOut:
    s = await _get_or_create_settings(session, tenant_id)

    changed: list[str] = []
    billplz_changed = False

    if body.billplz_api_key is not None:
        s.billplz_api_key = encrypt_secret(body.billplz_api_key)
        billplz_changed = True
    if body.billplz_collection_id is not None:
        s.billplz_collection_id = body.billplz_collection_id.strip() or None
        billplz_changed = True
    if body.billplz_xsign_key is not None:
        s.billplz_xsign_key = encrypt_secret(body.billplz_xsign_key)
        billplz_changed = True
    if body.billplz_mode is not None and body.billplz_mode != s.billplz_mode:
        s.billplz_mode = body.billplz_mode
        changed.append("billplz_mode")
        await audit(session, action="settings.billplz_mode", tenant_id=tenant_id,
                    user_id=user_claims.get("user_id"), meta={"mode": body.billplz_mode})

    for attr in ("receipt_footer", "shop_contact_email", "shop_contact_phone"):
        v = getattr(body, attr)
        if v is not None:
            setattr(s, attr, v)
            changed.append(attr)

    for attr in ("yolo_conf_threshold", "yolo_conf_minimum", "openai_daily_limit"):
        v = getattr(body, attr)
        if v is not None:
            setattr(s, attr, v)
            changed.append(attr)

    if billplz_changed:
        await audit(session, action="settings.billplz", tenant_id=tenant_id,
                    user_id=user_claims.get("user_id"),
                    meta={"api_key_set": bool(body.billplz_api_key),
                          "collection_set": bool(body.billplz_collection_id),
                          "xsign_set": bool(body.billplz_xsign_key)})
    if any(c in changed for c in ("receipt_footer", "shop_contact_email", "shop_contact_phone")):
        await audit(session, action="settings.branding", tenant_id=tenant_id,
                    user_id=user_claims.get("user_id"), meta={"fields": changed})
    if any(c in changed for c in ("yolo_conf_threshold", "yolo_conf_minimum", "openai_daily_limit")):
        await audit(session, action="settings.thresholds", tenant_id=tenant_id,
                    user_id=user_claims.get("user_id"), meta={"fields": changed})

    await session.commit()
    await session.refresh(s)
    return _to_out(s)


@router.post("/logo", dependencies=[Depends(require_role("owner"))])
async def upload_logo(file: UploadFile = File(...),
                      user_claims: dict = Depends(get_current_user),
                      tenant_id: int = Depends(get_tenant),
                      session: AsyncSession = Depends(get_session)) -> SettingsOut:
    if file.content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(status_code=400, detail=f"content_type must be one of {sorted(ALLOWED_LOGO_TYPES)}")

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(status_code=413, detail=f"logo max {MAX_LOGO_BYTES} bytes")

    # Resize longest edge to 1024 via Pillow (per plan)
    try:
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(data)).convert("RGBA")
        img.thumbnail((1024, 1024))
        out_dir = UPLOADS_DIR / str(tenant_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "logo.png"
        img.save(out_path, format="PNG")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid image: {e}")

    rel = f"/uploads/{tenant_id}/logo.png"
    s = await _get_or_create_settings(session, tenant_id)
    s.logo_path = rel
    await audit(session, action="settings.branding", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), meta={"logo_uploaded": True, "bytes": len(data)})
    await session.commit()
    await session.refresh(s)
    return _to_out(s)


# Internal helper (used by future Phase 8 Billplz service; NOT exposed via HTTP).
def get_billplz_credentials(s: TenantSettings) -> tuple[str | None, str | None, str | None, str]:
    return (
        decrypt_secret(s.billplz_api_key),
        s.billplz_collection_id,
        decrypt_secret(s.billplz_xsign_key),
        s.billplz_mode,
    )
