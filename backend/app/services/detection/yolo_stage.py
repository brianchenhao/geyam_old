"""Stage A — tenant's own YOLO weights."""
from typing import Any

from PIL import Image


def run_yolo(model: Any, img: Image.Image,
             conf_threshold: float, conf_minimum: float) -> list[dict]:
    """Returns list of {label, confidence, needs_confirm, source='yolo'}.

    - conf >= conf_threshold → needs_confirm=False (green)
    - conf_minimum <= conf < conf_threshold → needs_confirm=True (yellow)
    - conf < conf_minimum → dropped
    """
    if model is None:
        return []
    try:
        results = model.predict(img, conf=conf_minimum, iou=0.45, verbose=False)
    except Exception:
        return []

    out: list[dict] = []
    for r in results:
        names = r.names  # class_idx → label
        if r.boxes is None:
            continue
        for box in r.boxes:
            try:
                cls = int(box.cls[0].item())
                conf = float(box.conf[0].item())
            except Exception:
                continue
            if conf < conf_minimum:
                continue
            label = names.get(cls) if isinstance(names, dict) else names[cls]
            out.append({
                "label": label,
                "confidence": conf,
                "source": "yolo",
                "needs_confirm": conf < conf_threshold,
            })
    return out
