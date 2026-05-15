"""Phase 7 — POST /detect: tenant YOLO → MediaPipe → OpenAI cascade."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.deps import get_current_user, get_tenant
from app.services.detection.cascade import detect
from app.websocket import hub

router = APIRouter(tags=["detect"])

MAX_BYTES = 10 * 1024 * 1024
ALLOWED = {"image/png", "image/jpeg", "image/webp"}


class DetectItem(BaseModel):
    menu_item_id: int | None = None
    label: str | None = None
    name: str | None = None
    price: float | None = None
    confidence: float
    source: str
    needs_confirm: bool


class DetectOut(BaseModel):
    items: list[DetectItem]
    source_breakdown: dict[str, int]
    phash: str
    errors: list[str]


@router.post("/detect", response_model=DetectOut)
async def detect_endpoint(
    file: UploadFile = File(...),
    user_claims: dict = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant),
):
    if file.content_type not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"content_type must be in {sorted(ALLOWED)}")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="image too large")
    try:
        result = detect(tenant_id=tenant_id, image_bytes=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"detection failed: {type(e).__name__}")

    low_conf_items = [i for i in result.get("items", []) if i.get("needs_confirm")]
    if low_conf_items:
        await hub.publish(tenant_id, {
            "type": "low_conf",
            "count": len(low_conf_items),
            "items": [
                {"name": i.get("name") or i.get("label"),
                 "confidence": i.get("confidence"),
                 "source": i.get("source")}
                for i in low_conf_items
            ],
        })

    return DetectOut(**result)
