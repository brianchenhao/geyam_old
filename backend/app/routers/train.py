"""Phase 6 — owner uploads product videos → queue training jobs → 'Train Now'."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from redis import Redis
from rq import Queue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import REDIS_URL, UPLOADS_DIR
from app.deps import get_current_user, get_session, get_tenant, require_role
from app.models.menu_item import MenuItem
from app.models.model_version import ModelVersion
from app.models.tenant_settings import TenantSettings
from app.models.training_job import TrainingJob
from app.services.audit import audit
from app.services.video_frames import extract_middle_frame, probe_duration_seconds

router = APIRouter(tags=["training"])

MAX_VIDEO_BYTES = 100 * 1024 * 1024
MAX_VIDEO_SECONDS = 30
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm",
                       "video/x-matroska", "application/octet-stream"}

_redis: Optional[Redis] = None
_queue: Optional[Queue] = None


def _get_queue() -> Queue:
    global _redis, _queue
    if _queue is None:
        _redis = Redis.from_url(REDIS_URL)
        _queue = Queue("geyam", connection=_redis)
    return _queue


class TrainingJobOut(BaseModel):
    id: int
    menu_item_id: Optional[int] = None
    video_path: str
    status: str
    frames_extracted: int
    error: Optional[str] = None
    queued_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ModelVersionOut(BaseModel):
    id: int
    tenant_id: int
    filename: str
    num_classes: int
    accuracy: Optional[float] = None
    is_active: bool
    trained_at: datetime
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class ModelStatusOut(BaseModel):
    active: Optional[ModelVersionOut] = None
    history: list[ModelVersionOut]


@router.post("/train/video", dependencies=[Depends(require_role("owner"))])
async def upload_training_video(
    menu_item_id: int = Form(...),
    file: UploadFile = File(...),
    user_claims: dict = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> TrainingJobOut:
    if file.content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(status_code=400, detail=f"content_type must be in {sorted(ALLOWED_VIDEO_TYPES)}")

    item = (await session.execute(select(MenuItem).where(MenuItem.id == menu_item_id))).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="menu_item not found in this tenant")

    out_dir = UPLOADS_DIR / str(tenant_id) / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    tmp = out_dir / "upload.partial"
    with open(tmp, "wb") as fp:
        while True:
            chunk = await file.read(1024 * 256)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_VIDEO_BYTES:
                fp.close()
                try: tmp.unlink()
                except Exception: pass
                raise HTTPException(status_code=413, detail=f"video max {MAX_VIDEO_BYTES} bytes")
            fp.write(chunk)
    if total == 0:
        try: tmp.unlink()
        except Exception: pass
        raise HTTPException(status_code=400, detail="empty file")

    dur = probe_duration_seconds(tmp)
    if dur is None:
        try: tmp.unlink()
        except Exception: pass
        raise HTTPException(status_code=400, detail="could not probe video duration")
    if dur > MAX_VIDEO_SECONDS:
        try: tmp.unlink()
        except Exception: pass
        raise HTTPException(status_code=400, detail=f"video must be ≤{MAX_VIDEO_SECONDS}s (got {dur:.1f}s)")

    job = TrainingJob(
        tenant_id=tenant_id,
        menu_item_id=menu_item_id,
        video_path="",
        status="queued",
    )
    session.add(job)
    await session.flush()

    final_path = out_dir / f"{job.id}.mp4"
    tmp.rename(final_path)
    job.video_path = str(final_path)

    if not item.image_path:
        frame_dir = UPLOADS_DIR / str(tenant_id) / "products"
        frame_dir.mkdir(parents=True, exist_ok=True)
        frame_path = frame_dir / f"{item.id}.jpg"
        if extract_middle_frame(final_path, frame_path):
            item.image_path = f"/uploads/{tenant_id}/products/{item.id}.jpg"

    await audit(session, action="training.queue", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="training_job", entity_id=job.id,
                meta={"menu_item_id": menu_item_id, "seconds": dur, "bytes": total})
    await session.commit()
    await session.refresh(job)
    return TrainingJobOut.model_validate(job)


@router.post("/train/run", dependencies=[Depends(require_role("owner"))])
async def start_training(
    user_claims: dict = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> dict:
    ts = (await session.execute(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )).scalars().first()
    if ts is None:
        ts = TenantSettings(tenant_id=tenant_id)
        session.add(ts)
        await session.flush()

    if ts.training_locked_at is not None and ts.training_locked_at > datetime.utcnow() - timedelta(minutes=30):
        raise HTTPException(status_code=409, detail="training already in progress")

    queued = (await session.execute(
        select(TrainingJob).where(TrainingJob.tenant_id == tenant_id, TrainingJob.status == "queued")
    )).scalars().all()
    if not queued:
        raise HTTPException(status_code=400, detail="no queued training jobs")

    ts.training_locked_at = datetime.utcnow()
    await audit(session, action="training.start", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), meta={"job_count": len(queued)})
    await session.commit()

    q = _get_queue()
    rq_job = q.enqueue("app.services.training.run_batch", tenant_id, job_timeout="30m")
    return {"status": "started", "rq_job_id": rq_job.id, "job_count": len(queued)}


@router.get("/train/jobs", dependencies=[Depends(require_role("owner"))])
async def list_training_jobs(
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> list[TrainingJobOut]:
    res = await session.execute(select(TrainingJob).order_by(TrainingJob.id.desc()))
    return [TrainingJobOut.model_validate(j) for j in res.scalars().all()]


@router.get("/model/status", dependencies=[Depends(require_role("owner"))])
async def model_status(
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> ModelStatusOut:
    rows = (await session.execute(
        select(ModelVersion).order_by(ModelVersion.id.desc())
    )).scalars().all()
    active = next((r for r in rows if r.is_active), None)
    return ModelStatusOut(
        active=ModelVersionOut.model_validate(active) if active else None,
        history=[ModelVersionOut.model_validate(r) for r in rows],
    )
