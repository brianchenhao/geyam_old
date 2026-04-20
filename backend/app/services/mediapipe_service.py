"""MediaPipe EfficientDet-Lite0 generic-object detector (Phase 7 stage 2).

STUB: real MediaPipe on Windows requires `mediapipe` pip which has heavy native deps.
Returns [] for now; hot-swappable — the cascade falls through to OpenAI cleanly.
Replace with real detection once mediapipe is installed."""
from pathlib import Path


# Category alias table — maps generic COCO-ish labels into your menu categories.
# Used by the cascade to narrow candidates before asking the user to confirm.
CATEGORY_ALIASES: dict[str, str] = {
    "bottle": "drink",
    "cup": "drink",
    "wine glass": "drink",
    "can": "drink",
    "sandwich": "bakery",
    "donut": "bakery",
    "cake": "bakery",
    "pizza": "bakery",
    "hot dog": "snack",
    "banana": "snack",
    "apple": "snack",
    "orange": "snack",
    "carrot": "snack",
    "broccoli": "snack",
}


def detect(image_bytes: bytes) -> list[dict]:
    """Return list of generic detections. STUB — returns []."""
    return []


def shortlist_candidates(
    generic_label: str, menu_items: list[dict]
) -> list[dict]:
    """Given a generic label (e.g. 'bottle'), return menu items in the aliased category."""
    category = CATEGORY_ALIASES.get(generic_label.lower())
    if not category:
        return []
    return [m for m in menu_items if (m.get("category") or "").lower() == category]
