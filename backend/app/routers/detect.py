import io
from collections import Counter

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image
from sqlalchemy import select

from app.database import SessionLocal
from app.models.menu_item import MenuItem
from app.services import yolo_service
from app.services.openai_vision import VisionError, detect_with_vision

router = APIRouter(tags=["detect"])

MAX_SAME_ITEM = 3


def _build_detections(
    raw: list[dict],
    by_label: dict,
) -> tuple[list[dict], float]:
    """Turn raw YOLO dicts into the response shape + running total."""
    detections: list[dict] = []
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
    return detections, total


def _build_vision_detections(
    vision_items: list[dict],
    by_label: dict,
) -> tuple[list[dict], float]:
    """Expand vision's {label, quantity} into one entry per unit so the
    response shape matches YOLO's (frontend sums price across entries)."""
    detections: list[dict] = []
    total = 0.0
    for item in vision_items:
        mi = by_label.get(item["label"])
        if mi is None:
            continue
        price = float(mi.price)
        for _ in range(item["quantity"]):
            detections.append(
                {
                    "menu_item_id": mi.id,
                    "name": mi.name,
                    "price": price,
                    "confidence": round(item["confidence"], 3),
                    "box": [0.0, 0.0, 0.0, 0.0],
                }
            )
            total += price
    return detections, total


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

    async with SessionLocal() as session:
        rows = await session.scalars(select(MenuItem))
        menu_items = list(rows)
    by_label = {m.label: m for m in menu_items}

    counts = Counter(d["label"] for d in raw)
    max_same = max(counts.values(), default=0)

    if max_same <= MAX_SAME_ITEM:
        detections, total = _build_detections(raw, by_label)
        return {
            "detections": detections,
            "total": round(total, 2),
            "source": "yolo",
        }

    try:
        vision_items = await detect_with_vision(
            image_bytes,
            menu_labels=list(by_label.keys()),
            content_type=image.content_type or "image/jpeg",
        )
    except VisionError as e:
        detections, total = _build_detections(raw, by_label)
        return {
            "detections": detections,
            "total": round(total, 2),
            "source": "yolo",
            "warning": (
                f"YOLO detected {max_same} of one item (>{MAX_SAME_ITEM}); "
                f"vision fallback failed: {e}"
            ),
        }

    detections, total = _build_vision_detections(vision_items, by_label)
    return {
        "detections": detections,
        "total": round(total, 2),
        "source": "openai",
        "note": (
            f"YOLO flagged as unrealistic ({max_same}x one item); "
            f"verified with GPT-4o vision."
        ),
    }
