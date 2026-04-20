"""Phase 6 training service (runs in the RQ worker).

Flow:
  1. Mark all queued jobs for this tenant as 'training'.
  2. For each job: extract fps=2 frames and write auto-labels (centered 0.8x0.8).
  3. Run YOLO fine-tune if TRAIN_MODE='real', else copy baseline weights (stub).
  4. Record a new model_versions row (is_active=True, previous → is_active=False).
  5. Release tenant_settings.training_locked_at.
  6. On any exception: mark remaining jobs 'failed', release the lock, keep the
     old active model unchanged.
"""
import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import BASE_DIR
from app.models.menu_item import MenuItem
from app.models.model_version import ModelVersion
from app.models.tenant_settings import TenantSettings
from app.models.training_job import TrainingJob
from app.services.video_frames import extract_frames_at_fps


def _yaml_escape(s: str) -> str:
    return s.replace("'", "''")


def _sync_sessionmaker():
    sync_url = os.environ.get("ALEMBIC_DATABASE_URL") or \
        os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql+psycopg")
    engine = create_engine(sync_url, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _release_lock(session: Session, tenant_id: int) -> None:
    ts = session.execute(select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)).scalars().first()
    if ts is not None:
        ts.training_locked_at = None


def run_batch(tenant_id: int) -> dict:
    """Entry point called by the RQ worker."""
    Maker = _sync_sessionmaker()

    training_data_root = Path(os.environ.get("TRAINING_DATA_DIR", str(BASE_DIR / "training_data"))) / str(tenant_id)
    model_out_dir = Path(os.environ.get("MODEL_DIR", str(BASE_DIR / "ml_models"))) / str(tenant_id)
    model_out_dir.mkdir(parents=True, exist_ok=True)
    model_out_path = model_out_dir / "best.pt"

    results = {"frames": 0, "jobs": [], "failed": False, "error": None}

    with Maker() as s:
        queued = s.execute(
            select(TrainingJob).where(TrainingJob.tenant_id == tenant_id,
                                       TrainingJob.status == "queued")
        ).scalars().all()
        for j in queued:
            j.status = "training"
            j.started_at = datetime.utcnow()
        s.commit()

        if not queued:
            _release_lock(s, tenant_id); s.commit()
            results["error"] = "no queued jobs"
            return results

        try:
            items_by_label: dict[str, MenuItem] = {}
            item_by_id: dict[int, MenuItem] = {}
            for j in queued:
                if j.menu_item_id is None:
                    continue
                item = s.execute(select(MenuItem).where(MenuItem.id == j.menu_item_id)).scalars().first()
                if item is None:
                    continue
                items_by_label.setdefault(item.label, item)
                item_by_id[item.id] = item

            class_names = sorted(items_by_label.keys())
            class_idx = {n: i for i, n in enumerate(class_names)}

            images_dir = training_data_root / "images"
            labels_dir = training_data_root / "labels"
            images_dir.mkdir(parents=True, exist_ok=True)
            labels_dir.mkdir(parents=True, exist_ok=True)

            total_frames = 0
            for j in queued:
                item = item_by_id.get(j.menu_item_id)
                if item is None:
                    j.status = "failed"; j.error = "menu_item not found"; j.finished_at = datetime.utcnow()
                    continue

                per_video_dir = images_dir / f"job_{j.id}"
                n = extract_frames_at_fps(j.video_path, per_video_dir, fps=2, prefix=f"j{j.id}")
                j.frames_extracted = n
                total_frames += n

                cls = class_idx[item.label]
                for img in list(per_video_dir.glob("j*.jpg")):
                    target_img = images_dir / img.name
                    try:
                        shutil.move(str(img), str(target_img))
                    except Exception:
                        pass
                    label_path = labels_dir / (target_img.stem + ".txt")
                    label_path.write_text(f"{cls} 0.5 0.5 0.8 0.8\n", encoding="utf-8")

            results["frames"] = total_frames

            mode = os.environ.get("TRAIN_MODE", "stub").lower()
            accuracy = None
            if mode == "real" and total_frames > 0:
                from ultralytics import YOLO
                data_yaml = training_data_root / "data.yaml"
                data_yaml.write_text(
                    "path: " + str(training_data_root.resolve()) + "\n"
                    "train: images\nval: images\n"
                    f"nc: {len(class_names)}\n"
                    "names: [" + ", ".join(f"'{_yaml_escape(n)}'" for n in class_names) + "]\n",
                    encoding="utf-8",
                )
                base = YOLO(str(Path(BASE_DIR) / "yolov8n.pt"))
                out = base.train(
                    data=str(data_yaml),
                    epochs=int(os.environ.get("TRAIN_EPOCHS", "1")),
                    imgsz=640, batch=4, project=str(training_data_root / "runs"),
                    name="fit", exist_ok=True, verbose=False,
                )
                best_src = Path(out.save_dir) / "weights" / "best.pt"
                if best_src.exists():
                    shutil.copy(best_src, model_out_path)
            else:
                baseline = Path(BASE_DIR) / "yolov8n.pt"
                if not baseline.exists():
                    raise RuntimeError(f"baseline weights missing at {baseline}")
                shutil.copy(baseline, model_out_path)

            # Flip old model_versions to inactive, add new active row
            prev = s.execute(
                select(ModelVersion).where(ModelVersion.tenant_id == tenant_id,
                                            ModelVersion.is_active.is_(True))
            ).scalars().all()
            for p in prev:
                p.is_active = False

            s.add(ModelVersion(
                tenant_id=tenant_id, filename="best.pt",
                num_classes=max(len(class_names), 1),
                accuracy=accuracy, is_active=True,
                notes=("stub" if mode != "real" else "fine-tuned"),
            ))

            for j in queued:
                if j.status == "training":
                    j.status = "done"; j.finished_at = datetime.utcnow()

            results["jobs"] = [
                {"id": j.id, "status": j.status, "frames": j.frames_extracted} for j in queued
            ]
        except Exception as e:
            results["failed"] = True
            results["error"] = str(e)[:500]
            tb = traceback.format_exc()[:2000]
            for j in queued:
                if j.status == "training":
                    j.status = "failed"; j.error = tb; j.finished_at = datetime.utcnow()
        finally:
            _release_lock(s, tenant_id)
            s.commit()

    return results
