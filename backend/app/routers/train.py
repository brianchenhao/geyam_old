"""Phase 6 endpoints: queue status, Train Now batch trigger."""
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from redis import Redis
from rq import Queue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import Principal, get_session, require_role
from app.models import TenantSettings, TrainingJob
from app.services import audit

router = APIRouter(prefix="/train", tags=["training"])


class JobOut(BaseModel):
    id: int
    menu_item_id: int | None
    status: str
    video_path: str
    frames_extracted: int
    error: str | None

    model_config = {"from_attributes": True}


class TrainRunResult(BaseModel):
    enqueued: bool
    queued_jobs: int
    rq_job_id: str | None


def _queue() -> Queue:
    url = os.getenv("REDIS_URL", "redis://localhost:6380/0")
    return Queue("training", connection=Redis.from_url(url))


@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    rows = await session.scalars(
        select(TrainingJob).order_by(TrainingJob.id.desc())
    )
    return list(rows)


@router.post("/run", response_model=TrainRunResult)
async def run_training_now(
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    settings = await session.get(TenantSettings, p.tenant_id)
    if settings is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "settings missing")
    if settings.training_locked_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "training already in progress")

    queued = await session.scalar(
        select(TrainingJob.id)
        .where(TrainingJob.status == "queued")
        .limit(1)
    )
    if queued is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no queued training jobs")

    queued_count = await session.scalar(
        select(TrainingJob.id)
        .where(TrainingJob.status == "queued")
    )
    n = len((await session.scalars(
        select(TrainingJob.id).where(TrainingJob.status == "queued")
    )).all())

    settings.training_locked_at = datetime.utcnow()
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="training.run", meta={"queued_jobs": n},
    )
    await session.commit()

    try:
        q = _queue()
        rq_job = q.enqueue(
            "app.services.training.run_training",
            p.tenant_id, job_timeout=1800,
        )
        return TrainRunResult(enqueued=True, queued_jobs=n, rq_job_id=rq_job.id)
    except Exception as e:
        # Release lock if we couldn't enqueue.
        settings.training_locked_at = None
        await session.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"redis enqueue failed: {e}"
        )
