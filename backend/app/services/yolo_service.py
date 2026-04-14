"""YOLO model cache + inference.

The model is loaded once and held in memory. `reload_model()` is called after
training completes, which flips a flag so the next `get_model()` call re-reads
the latest weights from disk.
"""
from pathlib import Path
from typing import Any, Optional

from app.config import MODEL_DIR

_cached_model = None
_cached_path: Optional[Path] = None
_needs_reload = True


def find_latest_weights() -> Optional[Path]:
    if not MODEL_DIR.exists():
        return None
    pts = sorted(MODEL_DIR.glob("best_v*.pt"), key=_version_num)
    return pts[-1] if pts else None


def _version_num(path: Path) -> int:
    try:
        return int(path.stem.split("_v")[-1])
    except ValueError:
        return -1


def get_model():
    """Return the currently active YOLO model, or None if none trained yet."""
    global _cached_model, _cached_path, _needs_reload
    if not _needs_reload:
        return _cached_model

    path = find_latest_weights()
    if path is None:
        _cached_model = None
        _cached_path = None
    elif path != _cached_path:
        from ultralytics import YOLO  # lazy import

        _cached_model = YOLO(str(path))
        _cached_path = path
    _needs_reload = False
    return _cached_model


def reload_model() -> None:
    """Mark the cache stale. Next get_model() will re-scan ml_models/."""
    global _needs_reload
    _needs_reload = True


def detect(image: Any, conf: float = 0.25) -> list[dict]:
    """Run YOLO inference. `image` can be a PIL Image, numpy array, or path.

    Returns a list of raw detections: [{label, confidence, box: [x, y, w, h]}].
    Returns [] if no model is loaded OR nothing detected — callers should check
    get_model() separately if they need to distinguish those cases.
    """
    model = get_model()
    if model is None:
        return []
    results = model.predict(image, conf=conf, verbose=False)
    r = results[0]
    out: list[dict] = []
    names = r.names
    for box in r.boxes:
        cls_id = int(box.cls[0])
        label = names[cls_id]
        confidence = float(box.conf[0])
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        out.append(
            {
                "label": label,
                "confidence": confidence,
                "box": [x1, y1, x2 - x1, y2 - y1],
            }
        )
    return out
