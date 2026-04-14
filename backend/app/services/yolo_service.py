"""Lightweight YOLO model cache.

Lazy-imports ultralytics so /health and /model/status don't pay the import cost
until actual inference is needed.
"""
from pathlib import Path
from typing import Optional

from app.config import MODEL_DIR

_cached_model = None
_cached_path: Optional[Path] = None


def find_latest_weights() -> Optional[Path]:
    if not MODEL_DIR.exists():
        return None
    pts = sorted(
        MODEL_DIR.glob("best_v*.pt"),
        key=lambda p: _version_num(p),
    )
    return pts[-1] if pts else None


def _version_num(path: Path) -> int:
    try:
        return int(path.stem.split("_v")[-1])
    except ValueError:
        return -1


def get_model():
    """Return the currently active YOLO model, or None if none trained yet."""
    global _cached_model, _cached_path
    path = find_latest_weights()
    if path is None:
        _cached_model = None
        _cached_path = None
        return None
    if _cached_path != path:
        from ultralytics import YOLO  # lazy import

        _cached_model = YOLO(str(path))
        _cached_path = path
    return _cached_model


def reload_model() -> None:
    """Force the next get_model() call to re-read the latest weights file."""
    global _cached_model, _cached_path
    _cached_model = None
    _cached_path = None
