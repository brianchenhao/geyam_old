"""Per-tenant YOLO model LRU cache.

Keep at most 3 tenants' YOLO weights resident in memory at a time. Next /detect
call for a tenant with no cached model loads it from disk (~1s) and evicts the
oldest tenant if at capacity.

Used by the Phase 7 detection cascade and the Phase 6 post-training hot reload
(call `invalidate(tenant_id)` after a new best.pt is written; next /detect
reloads the new weights).
"""
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from app.config import BASE_DIR

MODEL_DIR = Path(BASE_DIR) / "ml_models"
LRU_CAPACITY = 3


_cache: "OrderedDict[int, tuple[object, float]]" = OrderedDict()


def _tenant_weights_path(tenant_id: int) -> Path:
    return MODEL_DIR / str(tenant_id) / "best.pt"


def get_model(tenant_id: int) -> Optional[object]:
    """Return loaded YOLO model, or None if the tenant has no weights yet.

    Auto-reloads when best.pt on disk is newer than the cached copy — this is
    how Phase 6's training worker (separate process) triggers hot-reload here.
    """
    path = _tenant_weights_path(tenant_id)
    if not path.exists():
        _cache.pop(tenant_id, None)
        return None

    disk_mtime = path.stat().st_mtime
    cached = _cache.get(tenant_id)
    if cached is not None and cached[1] >= disk_mtime:
        _cache.move_to_end(tenant_id)
        return cached[0]

    try:
        from ultralytics import YOLO
        model = YOLO(str(path))
    except Exception:
        return None

    _cache[tenant_id] = (model, disk_mtime)
    _cache.move_to_end(tenant_id)
    while len(_cache) > LRU_CAPACITY:
        _cache.popitem(last=False)
    return model


def invalidate(tenant_id: int) -> None:
    _cache.pop(tenant_id, None)
