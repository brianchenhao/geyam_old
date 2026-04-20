"""Phase 7: POST /detect runs the 3-stage cascade against the tray photo."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import Principal, get_session, require_role
from app.services import cascade

router = APIRouter(prefix="/detect", tags=["detect"])

ALLOWED = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 10 * 1024 * 1024


@router.post("")
async def detect(
    file: UploadFile = File(...),
    p: Principal = Depends(require_role("owner", "cashier")),
    session: AsyncSession = Depends(get_session),
):
    if file.content_type not in ALLOWED:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "jpeg/png/webp only")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "image > 10MB")

    result = await cascade.run(session, tenant_id=p.tenant_id, image_bytes=data)
    await session.commit()  # persist pHash cache + openai_usage bumps
    return result
