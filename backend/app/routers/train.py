import tempfile
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy import select

from app.database import SessionLocal
from app.models.menu_item import MenuItem
from app.models.model_version import ModelVersion
from app.services.training import run_training_pipeline, slugify

router = APIRouter(tags=["training"])


@router.post("/train/video")
async def train_video(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    price: float = Form(...),
    video: UploadFile = File(...),
):
    if price <= 0:
        raise HTTPException(400, "price must be > 0")
    if not name.strip():
        raise HTTPException(400, "name is required")
    if not (video.content_type or "").startswith("video/"):
        raise HTTPException(400, "file must be a video")

    label = slugify(name)
    if not label:
        raise HTTPException(400, "name produced an empty label")

    async with SessionLocal() as session:
        existing = await session.scalar(
            select(MenuItem).where(MenuItem.label == label)
        )
    if existing:
        raise HTTPException(
            409, f"product with label '{label}' already exists"
        )

    suffix = Path(video.filename or "upload.mp4").suffix or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await video.read())
        tmp_path = Path(tmp.name)

    background_tasks.add_task(
        run_training_pipeline, tmp_path, name.strip(), label, float(price)
    )
    return {
        "status": "training started",
        "name": name.strip(),
        "label": label,
        "price": price,
    }


@router.get("/model/status")
async def model_status():
    async with SessionLocal() as session:
        row = await session.scalar(
            select(ModelVersion)
            .where(ModelVersion.is_active.is_(True))
            .order_by(ModelVersion.id.desc())
        )
    if row is None:
        return {"active": False, "message": "no model trained yet"}
    return {
        "active": True,
        "filename": row.filename,
        "num_classes": row.num_classes,
        "accuracy": row.accuracy,
        "trained_at": row.trained_at.isoformat() if row.trained_at else None,
        "notes": row.notes,
    }
