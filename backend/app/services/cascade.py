"""3-stage detection cascade: YOLO → MediaPipe → OpenAI.

Each stage can add items or fall through. Every returned item carries a
`source` so the UI can render the right confidence badge, and a
`needs_confirm` flag for low-confidence YOLO / MediaPipe suggestions."""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MenuItem, TenantSettings
from app.services import mediapipe_service, openai_vision, yolo_service
from app.services.openai_vision import OpenAIDisabled, QuotaExceeded


@dataclass
class DetectedItem:
    menu_item_id: int | None
    name: str
    label: str
    price: float
    confidence: float
    source: str  # 'yolo' | 'yolo_low' | 'mediapipe' | 'openai' | 'shortlist'
    needs_confirm: bool

    def to_dict(self) -> dict:
        return {
            "menu_item_id": self.menu_item_id,
            "name": self.name,
            "label": self.label,
            "price": self.price,
            "confidence": self.confidence,
            "source": self.source,
            "needs_confirm": self.needs_confirm,
        }


async def run(
    session: AsyncSession, *, tenant_id: int, image_bytes: bytes
) -> dict:
    """Returns {items: [...], shortlists: [...], notes: "..."}"""
    settings = await session.get(TenantSettings, tenant_id)
    conf_threshold = float(settings.yolo_conf_threshold) if settings else 0.60
    conf_minimum = float(settings.yolo_conf_minimum) if settings else 0.40
    openai_limit = settings.openai_daily_limit if settings else 50

    menu_rows = (await session.scalars(
        select(MenuItem).where(MenuItem.is_active == True)  # noqa: E712
    )).all()
    by_label = {m.label: m for m in menu_rows}
    by_name = {m.name: m for m in menu_rows}
    menu_payload = [
        {"id": m.id, "name": m.name, "label": m.label, "category": m.category}
        for m in menu_rows
    ]

    items: list[DetectedItem] = []
    shortlists: list[dict] = []
    notes: list[str] = []

    # Stage 1: tenant YOLO
    try:
        raw_yolo = yolo_service.detect(tenant_id, image_bytes, conf=conf_minimum)
    except Exception as e:
        raw_yolo = []
        notes.append(f"yolo error: {e}")

    yolo_matched = False
    for det in raw_yolo:
        m = by_label.get(det["label"])
        if m is None:
            continue
        yolo_matched = True
        conf = det["confidence"]
        if conf >= conf_threshold:
            items.append(DetectedItem(
                menu_item_id=m.id, name=m.name, label=m.label,
                price=float(m.price), confidence=conf,
                source="yolo", needs_confirm=False,
            ))
        elif conf >= conf_minimum:
            items.append(DetectedItem(
                menu_item_id=m.id, name=m.name, label=m.label,
                price=float(m.price), confidence=conf,
                source="yolo_low", needs_confirm=True,
            ))

    if items:
        return {"items": [i.to_dict() for i in items], "shortlists": shortlists, "notes": notes}

    # Stage 2: MediaPipe generic detector → shortlists
    try:
        mp_dets = mediapipe_service.detect(image_bytes)
    except Exception as e:
        mp_dets = []
        notes.append(f"mediapipe error: {e}")

    for d in mp_dets:
        candidates = mediapipe_service.shortlist_candidates(d.get("label", ""), menu_payload)
        if len(candidates) == 1:
            c = candidates[0]
            m = by_name.get(c["name"])
            if m:
                items.append(DetectedItem(
                    menu_item_id=m.id, name=m.name, label=m.label,
                    price=float(m.price), confidence=float(d.get("confidence", 0.5)),
                    source="mediapipe", needs_confirm=True,
                ))
        elif len(candidates) > 1:
            shortlists.append({
                "generic_label": d.get("label"),
                "candidates": candidates,
            })

    if items or shortlists:
        return {"items": [i.to_dict() for i in items], "shortlists": shortlists, "notes": notes}

    # Stage 3: OpenAI vision
    try:
        found_names, src = await openai_vision.detect(
            session, tenant_id=tenant_id, image_bytes=image_bytes,
            menu_names=list(by_name.keys()), daily_limit=openai_limit,
        )
    except (QuotaExceeded, OpenAIDisabled) as e:
        notes.append(str(e))
        found_names, src = [], "openai.skip"
    except Exception as e:
        notes.append(f"openai error: {e}")
        found_names, src = [], "openai.skip"

    for n in found_names:
        m = by_name.get(n)
        if m is None:
            continue
        items.append(DetectedItem(
            menu_item_id=m.id, name=m.name, label=m.label,
            price=float(m.price), confidence=0.0, source=src,
            needs_confirm=True,
        ))

    if yolo_matched:
        notes.append("yolo saw below-threshold matches that were dropped")
    return {"items": [i.to_dict() for i in items], "shortlists": shortlists, "notes": notes}
