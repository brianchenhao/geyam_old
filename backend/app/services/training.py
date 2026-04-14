"""Video → YOLO training pipeline.

Flow per upload:
  1. Extract frames with ffmpeg (2 fps)
  2. 80/20 split into training_data/images/{train,val}/
  3. Write YOLO label .txt files (centered bbox, single class per frame)
  4. Append new class to training_data/data.yaml
  5. Fine-tune YOLOv8 from last best.pt (or yolov8n.pt if none)
  6. Copy resulting best.pt to ml_models/best_v{N}.pt
  7. Insert MenuItem + ModelVersion rows (new version = is_active, previous deactivated)

All heavy work runs inside asyncio.to_thread so the FastAPI event loop stays
responsive while training is in progress.
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
from pathlib import Path

import yaml
from sqlalchemy import update

from app.config import MODEL_DIR, TRAINING_DATA_DIR
from app.database import SessionLocal
from app.models.menu_item import MenuItem
from app.models.model_version import ModelVersion
from app.services import yolo_service

logger = logging.getLogger(__name__)

FPS = 2
EPOCHS = 30
IMG_SIZE = 640
TRAIN_VAL_SPLIT = 0.8


def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")[:50]


# ---------- sync helpers (run inside to_thread) ----------

def _extract_frames(video_path: Path, out_dir: Path, label: str) -> list[Path]:
    import imageio_ffmpeg

    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / f"{label}_%04d.jpg")
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps={FPS}",
        "-q:v",
        "2",
        pattern,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-400:]}")
    return sorted(out_dir.glob(f"{label}_*.jpg"))


def _split_frames(
    frames: list[Path], label: str
) -> tuple[list[Path], list[Path]]:
    train_dir = TRAINING_DATA_DIR / "images" / "train"
    val_dir = TRAINING_DATA_DIR / "images" / "val"
    train_dir.mkdir(parents=True, exist_ok=True)
    val_dir.mkdir(parents=True, exist_ok=True)

    split_idx = max(1, int(len(frames) * TRAIN_VAL_SPLIT))
    train_src = frames[:split_idx]
    val_src = frames[split_idx:] or frames[-1:]  # guarantee at least 1 val frame

    moved_train: list[Path] = []
    moved_val: list[Path] = []
    for f in train_src:
        dest = train_dir / f.name
        shutil.move(str(f), str(dest))
        moved_train.append(dest)
    for f in val_src:
        dest = val_dir / f.name
        if dest.exists():
            continue
        shutil.move(str(f), str(dest))
        moved_val.append(dest)
    return moved_train, moved_val


def _write_labels(frames: list[Path], split: str, class_id: int) -> None:
    label_dir = TRAINING_DATA_DIR / "labels" / split
    label_dir.mkdir(parents=True, exist_ok=True)
    for f in frames:
        label_file = label_dir / (f.stem + ".txt")
        label_file.write_text(f"{class_id} 0.5 0.5 0.8 0.8\n")


def _update_data_yaml(label: str, class_id: int) -> Path:
    yaml_path = TRAINING_DATA_DIR / "data.yaml"
    if yaml_path.exists():
        data = yaml.safe_load(yaml_path.read_text()) or {}
    else:
        data = {}
    data["path"] = str(TRAINING_DATA_DIR.resolve())
    data["train"] = "images/train"
    data["val"] = "images/val"
    names = data.get("names") or {}
    names = {int(k): v for k, v in names.items()}
    names[class_id] = label
    data["names"] = names
    yaml_path.write_text(yaml.safe_dump(data, sort_keys=False))
    return yaml_path


def _next_class_id() -> int:
    yaml_path = TRAINING_DATA_DIR / "data.yaml"
    if not yaml_path.exists():
        return 0
    data = yaml.safe_load(yaml_path.read_text()) or {}
    names = data.get("names") or {}
    if not names:
        return 0
    return max(int(k) for k in names.keys()) + 1


def _next_version() -> int:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    versions: list[int] = []
    for p in MODEL_DIR.glob("best_v*.pt"):
        try:
            versions.append(int(p.stem.split("_v")[-1]))
        except ValueError:
            pass
    return (max(versions) + 1) if versions else 1


def _base_weights() -> str:
    latest = yolo_service.find_latest_weights()
    return str(latest) if latest else "yolov8n.pt"


def _train_yolo(data_yaml: Path, version: int) -> tuple[Path, float | None]:
    from ultralytics import YOLO  # lazy import — ~2s

    model = YOLO(_base_weights())
    run_name = f"train_v{version}"
    results = model.train(
        data=str(data_yaml),
        epochs=EPOCHS,
        imgsz=IMG_SIZE,
        project=str(MODEL_DIR / "runs"),
        name=run_name,
        exist_ok=True,
    )
    src = MODEL_DIR / "runs" / run_name / "weights" / "best.pt"
    dest = MODEL_DIR / f"best_v{version}.pt"
    shutil.copy(str(src), str(dest))

    accuracy: float | None = None
    try:
        accuracy = float(results.box.map50)  # type: ignore[attr-defined]
    except Exception:
        pass
    return dest, accuracy


def _do_training_sync(
    video_path: Path, label: str
) -> tuple[Path, float | None, int, int, int]:
    """Runs entirely inside a worker thread. Returns
    (weights_path, accuracy, frame_count, class_id, version)."""
    class_id = _next_class_id()
    version = _next_version()

    tmp_frames_dir = TRAINING_DATA_DIR / "_tmp" / label
    if tmp_frames_dir.exists():
        shutil.rmtree(tmp_frames_dir)
    frames = _extract_frames(video_path, tmp_frames_dir, label)
    if not frames:
        raise RuntimeError("no frames extracted from video")

    train_frames, val_frames = _split_frames(frames, label)
    _write_labels(train_frames, "train", class_id)
    _write_labels(val_frames, "val", class_id)
    data_yaml = _update_data_yaml(label, class_id)

    weights_path, accuracy = _train_yolo(data_yaml, version)

    shutil.rmtree(tmp_frames_dir, ignore_errors=True)
    return weights_path, accuracy, len(frames), class_id, version


# ---------- async orchestration (called from BackgroundTasks) ----------

async def run_training_pipeline(
    video_path: Path, name: str, label: str, price: float
) -> None:
    try:
        (
            weights_path,
            accuracy,
            frame_count,
            class_id,
            version,
        ) = await asyncio.to_thread(_do_training_sync, video_path, label)

        async with SessionLocal() as session:
            await session.execute(
                update(ModelVersion).values(is_active=False)
            )
            session.add(
                ModelVersion(
                    filename=weights_path.name,
                    num_classes=class_id + 1,
                    accuracy=accuracy,
                    is_active=True,
                    notes=f"trained on {label}",
                )
            )
            session.add(
                MenuItem(
                    name=name,
                    label=label,
                    price=price,
                    frame_count=frame_count,
                )
            )
            await session.commit()

        yolo_service.reload_model()
        logger.info(
            "training complete: %s (class_id=%s version=%s) → %s",
            name,
            class_id,
            version,
            weights_path,
        )
    except Exception:
        logger.exception("training pipeline failed for %s", name)
    finally:
        try:
            video_path.unlink(missing_ok=True)
        except Exception:
            pass
