"""Stage B — MediaPipe EfficientDet-Lite0 + category alias → tenant menu shortlist.

Best-effort: if mediapipe import fails (common on some platforms), this stage
returns a clean empty result and the cascade continues to OpenAI.
"""
from typing import Any

from PIL import Image

# Category alias table — MediaPipe generic class → tenant menu_item.category
CATEGORY_ALIAS: dict[str, set[str]] = {
    "bottle": {"drink"},
    "cup": {"drink"},
    "wine glass": {"drink"},
    "can": {"drink"},
    "bowl": {"snack", "instant"},
    "box": {"snack"},
    "package": {"snack", "instant"},
    "donut": {"snack"},
    "sandwich": {"snack"},
    "cake": {"snack"},
}


def _try_load_detector():
    try:
        import mediapipe as mp  # noqa: F401
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision
        # Lazy-load a default EfficientDet-Lite0 from MediaPipe hub is complex to bundle;
        # for now we short-circuit (return None) and rely on YOLO + OpenAI. Slot is reserved
        # so when a model file is placed at ml_models/_shared/mediapipe_efficientdet.tflite
        # the loader can wire it.
        return None
    except Exception:
        return None


_detector = None


def run_mediapipe(img: Image.Image, menu_items: list[dict]) -> list[dict]:
    """Returns suggestions with source='mediapipe'.

    Each suggestion is either a single candidate (needs_confirm=True) or a
    shortlist placeholder with a candidates list for the cashier to pick from.
    """
    global _detector
    if _detector is None:
        _detector = _try_load_detector()
    if _detector is None:
        return []

    # Inference would go here. For Phase 7, returning [] means the cascade falls
    # through to OpenAI. Lands real detector in a follow-up when a tflite weight
    # file is bundled.
    return []


def category_shortlist(category_guess: str, menu_items: list[dict]) -> list[dict]:
    aliases = CATEGORY_ALIAS.get(category_guess.lower(), set())
    if not aliases:
        return []
    return [m for m in menu_items
            if (m.get("category") or "").lower() in aliases and m.get("is_active")]
