"""Phase 7 orchestrator: tenant YOLO -> MediaPipe shortlist -> OpenAI fallback."""
import os
from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.menu_item import MenuItem
from app.models.tenant_settings import TenantSettings
from app.services.detection.mediapipe_stage import run_mediapipe
from app.services.detection.openai_stage import run_openai
from app.services.detection.preprocess import load_and_prep, perceptual_hash
from app.services.detection.yolo_stage import run_yolo
from app.services.yolo_cache import get_model


def _sync_session():
    sync_url = os.environ.get("ALEMBIC_DATABASE_URL") or \
        os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql+psycopg")
    engine = create_engine(sync_url, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def detect(
    *,
    tenant_id: int,
    image_bytes: bytes,
) -> dict:
    """Top-level detection entry point. Returns the plan's response shape."""
    img = load_and_prep(image_bytes)
    phash = perceptual_hash(img)

    Maker = _sync_session()
    with Maker() as s:
        settings = s.execute(
            select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
        ).scalars().first()
        if settings is None:
            settings = TenantSettings(tenant_id=tenant_id)

        menu_rows = s.execute(
            select(MenuItem).where(MenuItem.tenant_id == tenant_id, MenuItem.is_active.is_(True))
        ).scalars().all()
        menu_items = [
            {"id": m.id, "name": m.name, "label": m.label, "price": float(m.price),
             "category": m.category, "is_active": m.is_active}
            for m in menu_rows
        ]
        label_to_item = {m["label"]: m for m in menu_items}

        errors: list[str] = []

        # Stage A — tenant YOLO
        model = get_model(tenant_id)
        yolo_items = run_yolo(
            model, img,
            conf_threshold=settings.yolo_conf_threshold or 0.60,
            conf_minimum=settings.yolo_conf_minimum or 0.40,
        )
        for it in yolo_items:
            match = label_to_item.get(it["label"])
            if match:
                it["menu_item_id"] = match["id"]
                it["name"] = match["name"]
                it["price"] = match["price"]
        yolo_items = [it for it in yolo_items if "menu_item_id" in it]

        # Stage B — MediaPipe (skipped when library unavailable; reserved slot)
        mp_items: list[dict] = []
        if not yolo_items:
            mp_items = run_mediapipe(img, menu_items)

        # Stage C — OpenAI (gated by yolo+mp empty)
        ai_items: list[dict] = []
        if not yolo_items and not mp_items:
            ai_items, err = run_openai(
                tenant_id=tenant_id, phash=phash, img=img,
                menu_items=menu_items, sync_session=s, settings=settings,
            )
            if err:
                errors.append(err)

        all_items = yolo_items + mp_items + ai_items

        # Deduplicate by menu_item_id keeping highest confidence
        dedup: dict[int, dict] = {}
        for it in all_items:
            mid = it.get("menu_item_id")
            if mid is None:
                continue
            if mid not in dedup or it["confidence"] > dedup[mid]["confidence"]:
                dedup[mid] = it

        final = list(dedup.values())

        return {
            "items": final,
            "source_breakdown": {
                "yolo": sum(1 for i in final if i["source"] == "yolo"),
                "mediapipe": sum(1 for i in final if i["source"] == "mediapipe"),
                "openai": sum(1 for i in final if i["source"] == "openai"),
            },
            "phash": phash,
            "errors": errors,
        }
