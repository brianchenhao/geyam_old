"""Per-tenant YOLO model cache and detection wrapper."""
import io
import threading
from pathlib import Path

import numpy as np
from PIL import Image
from ultralytics import YOLO

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models"
PRETRAINED = Path(__file__).resolve().parent.parent.parent / "yolov8n.pt"

_cache: dict[int, YOLO] = {}
_cache_lock = threading.Lock()


def active_model_path(tenant_id: int) -> Path:
    return MODELS_DIR / str(tenant_id) / "best.pt"


def get_model(tenant_id: int) -> YOLO:
    with _cache_lock:
        if tenant_id in _cache:
            return _cache[tenant_id]
        path = active_model_path(tenant_id)
        if not path.exists():
            path = PRETRAINED if PRETRAINED.exists() else Path("yolov8n.pt")
        model = YOLO(str(path))
        _cache[tenant_id] = model
        return model


def invalidate(tenant_id: int) -> None:
    with _cache_lock:
        _cache.pop(tenant_id, None)


def detect(tenant_id: int, image_bytes: bytes, conf: float = 0.25) -> list[dict]:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.array(img)
    results = get_model(tenant_id).predict(arr, conf=conf, verbose=False)
    out: list[dict] = []
    for r in results:
        names = r.names
        for b in r.boxes:
            cls = int(b.cls[0])
            label = names.get(cls, str(cls)) if isinstance(names, dict) else names[cls]
            out.append({
                "label": label,
                "confidence": float(b.conf[0]),
                "bbox": [float(x) for x in b.xyxy[0].tolist()],
            })
    return out
