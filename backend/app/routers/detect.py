import io

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image
from sqlalchemy import select

from app.database import SessionLocal
from app.models.menu_item import MenuItem
from app.services import yolo_service

router = APIRouter(tags=["detect"])


@router.post("/detect")
async def detect(image: UploadFile = File(...), conf: float = 0.25):
    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(400, "file must be an image")

    if yolo_service.get_model() is None:
        return {"error": "no model trained yet"}

    image_bytes = await image.read()
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        raise HTTPException(400, "could not decode image")

    raw = yolo_service.detect(img, conf=conf)
    if not raw:
        return {"detections": [], "total": 0.0}

    labels = {d["label"] for d in raw}
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(MenuItem).where(MenuItem.label.in_(labels))
        )
        by_label = {m.label: m for m in rows}

    detections = []
    total = 0.0
    for d in raw:
        mi = by_label.get(d["label"])
        if mi is None:
            continue
        price = float(mi.price)
        detections.append(
            {
                "menu_item_id": mi.id,
                "name": mi.name,
                "price": price,
                "confidence": round(d["confidence"], 3),
                "box": [round(v, 1) for v in d["box"]],
            }
        )
        total += price

    return {"detections": detections, "total": round(total, 2)}
