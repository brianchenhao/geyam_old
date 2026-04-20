"""Training pipeline (per-tenant batched).

Fast path: extract frames fps=2, auto-label centered 0.8x0.8 box per frame,
write YOLO data.yaml, run YOLO.train (1 epoch in dev), save best.pt.

On success or failure, training_locked_at is cleared — the API-level /train/run
endpoint holds the lock only until it enqueues; the worker clears it when
done."""
import asyncio
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import yaml
from sqlalchemy import select

import imageio_ffmpeg

from app.database import SessionLocal
from app.models import MenuItem, ModelVersion, TenantSettings, TrainingJob
from app.services import yolo_service

log = logging.getLogger("training")
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
UPLOADS = BACKEND_ROOT / "uploads"
MODELS = BACKEND_ROOT / "ml_models"
TRAINING_DATA = BACKEND_ROOT / "training_data"


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _extract_frames(video_path: Path, out_dir: Path, fps: int = 2) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "f%05d.jpg")
    cmd = [_ffmpeg(), "-y", "-i", str(video_path), "-vf", f"fps={fps}",
           "-q:v", "3", pattern]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg frames failed: {res.stderr[-500:]}")
    return len(list(out_dir.glob("f*.jpg")))


def _write_auto_labels(frames_dir: Path, class_id: int) -> None:
    """Centered 0.8x0.8 box in YOLO normalized format: `cx cy w h` = 0.5 0.5 0.8 0.8."""
    for jpg in frames_dir.glob("f*.jpg"):
        jpg.with_suffix(".txt").write_text(f"{class_id} 0.5 0.5 0.8 0.8\n")


def _build_dataset(tenant_id: int, items: list[MenuItem]) -> tuple[Path, list[str]]:
    """Stage images+labels under training_data/<tenant>/images/<split>/... and
    return (data.yaml path, ordered class names)."""
    root = TRAINING_DATA / str(tenant_id)
    if root.exists():
        shutil.rmtree(root)
    img_train = root / "images" / "train"
    lbl_train = root / "labels" / "train"
    img_train.mkdir(parents=True, exist_ok=True)
    lbl_train.mkdir(parents=True, exist_ok=True)

    names = [m.label for m in items]
    for cls_id, m in enumerate(items):
        src = UPLOADS / str(tenant_id) / "frames" / str(m.id)
        if not src.exists():
            continue
        for jpg in src.glob("f*.jpg"):
            dest_img = img_train / f"item{m.id}_{jpg.name}"
            dest_lbl = lbl_train / f"item{m.id}_{jpg.stem}.txt"
            shutil.copy2(jpg, dest_img)
            dest_lbl.write_text(f"{cls_id} 0.5 0.5 0.8 0.8\n")

    yaml_path = root / "data.yaml"
    # Duplicate train as val so YOLO gets a val set — fine for tiny dev runs.
    yaml_path.write_text(yaml.safe_dump({
        "path": str(root),
        "train": "images/train",
        "val": "images/train",
        "nc": len(names),
        "names": names,
    }))
    return yaml_path, names


def run_training(tenant_id: int, epochs: int = 1, imgsz: int = 320) -> dict:
    """Synchronous training entry point. Called by the RQ worker.
    Never raises externally — returns {status, accuracy, error}."""
    asyncio_result: dict = {}
    asyncio.run(_run_training_async(tenant_id, epochs, imgsz, asyncio_result))
    return asyncio_result


async def _run_training_async(
    tenant_id: int, epochs: int, imgsz: int, out: dict
) -> None:
    async with SessionLocal() as session:
        jobs = (await session.scalars(
            select(TrainingJob)
            .where(TrainingJob.tenant_id == tenant_id,
                   TrainingJob.status == "queued")
            .execution_options(skip_tenant_filter=True)
        )).all()
        items = (await session.scalars(
            select(MenuItem)
            .where(MenuItem.tenant_id == tenant_id)
            .execution_options(skip_tenant_filter=True)
        )).all()
        items_by_id = {m.id: m for m in items}

        if not jobs:
            await _release_lock(session, tenant_id)
            out.update({"status": "noop", "accuracy": None, "error": "no queued jobs"})
            return

        for job in jobs:
            job.status = "training"
            job.started_at = datetime.utcnow()
        await session.commit()

        try:
            frame_count_per_item: dict[int, int] = {}
            for job in jobs:
                if job.menu_item_id is None:
                    continue
                vp = BACKEND_ROOT / job.video_path.lstrip("/")
                frames_dir = UPLOADS / str(tenant_id) / "frames" / str(job.menu_item_id)
                n = _extract_frames(vp, frames_dir)
                job.frames_extracted = n
                frame_count_per_item[job.menu_item_id] = (
                    frame_count_per_item.get(job.menu_item_id, 0) + n
                )

            items_with_frames = [items_by_id[i] for i in frame_count_per_item
                                 if i in items_by_id]
            if not items_with_frames:
                raise RuntimeError("no frames extracted")

            yaml_path, names = _build_dataset(tenant_id, items_with_frames)

            # YOLO fine-tune.
            from ultralytics import YOLO
            base = yolo_service.PRETRAINED
            model = YOLO(str(base) if base.exists() else "yolov8n.pt")
            runs_dir = MODELS / str(tenant_id) / "runs"
            runs_dir.mkdir(parents=True, exist_ok=True)
            result = model.train(
                data=str(yaml_path), epochs=epochs, imgsz=imgsz, batch=4,
                project=str(runs_dir), name="train", exist_ok=True,
                verbose=False, plots=False,
            )
            best = Path(result.save_dir) / "weights" / "best.pt"
            target = MODELS / str(tenant_id) / "best.pt"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(best, target)

            accuracy = None
            try:
                metrics = result.results_dict if hasattr(result, "results_dict") else {}
                accuracy = float(metrics.get("metrics/mAP50(B)", 0.0))
            except Exception:
                accuracy = None

            session.add(ModelVersion(
                tenant_id=tenant_id, filename=str(target),
                num_classes=len(names), accuracy=accuracy, is_active=True,
                notes=f"epochs={epochs} items={len(items_with_frames)}",
            ))

            for job in jobs:
                # Only items that contributed frames count as 'done'.
                if job.menu_item_id in frame_count_per_item and job.frames_extracted > 0:
                    job.status = "done"
                    job.finished_at = datetime.utcnow()
                else:
                    job.status = "failed"
                    job.error = "no frames extracted"
                    job.finished_at = datetime.utcnow()

            for mi in items_with_frames:
                mi.frame_count = frame_count_per_item.get(mi.id, 0)

            await _release_lock(session, tenant_id)
            await session.commit()
            yolo_service.invalidate(tenant_id)
            out.update({"status": "done", "accuracy": accuracy, "error": None})

        except Exception as e:
            log.exception("training failed")
            for job in jobs:
                if job.status == "training":
                    job.status = "failed"
                    job.error = str(e)[:500]
                    job.finished_at = datetime.utcnow()
            await _release_lock(session, tenant_id)
            await session.commit()
            out.update({"status": "failed", "accuracy": None, "error": str(e)})


async def _release_lock(session, tenant_id: int) -> None:
    s = await session.get(TenantSettings, tenant_id)
    if s is not None:
        s.training_locked_at = None
