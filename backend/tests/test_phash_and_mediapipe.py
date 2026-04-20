"""Phase 7 gates: phash stable, mediapipe shortlist maps categories."""
import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import mediapipe_service, phash  # noqa: E402


def _png(w=32, h=32, color=(180, 80, 40)) -> bytes:
    img = Image.new("RGB", (w, h), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_phash_stable_same_image():
    a = _png(color=(100, 200, 50))
    b = _png(color=(100, 200, 50))
    assert phash.compute(a) == phash.compute(b)


def test_phash_differs_on_different_image():
    """Two very different patterns must hash differently. aHash on a solid
    color collapses to all zeros, so use structured patterns here."""
    import numpy as np

    def _pattern_png(pattern: np.ndarray) -> bytes:
        img = Image.fromarray(pattern, mode="RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    a = np.zeros((32, 32, 3), dtype=np.uint8)
    a[:16] = 255  # top half white
    b = np.zeros((32, 32, 3), dtype=np.uint8)
    b[:, :16] = 255  # left half white
    assert phash.compute(_pattern_png(a)) != phash.compute(_pattern_png(b))


def test_shortlist_bottle_maps_to_drinks():
    menu = [
        {"id": 1, "name": "Mineral Water 500ml", "label": "mineral_water", "category": "drink"},
        {"id": 2, "name": "Oreo", "label": "oreo", "category": "snack"},
    ]
    out = mediapipe_service.shortlist_candidates("bottle", menu)
    assert [m["name"] for m in out] == ["Mineral Water 500ml"]


def test_shortlist_unknown_label_empty():
    assert mediapipe_service.shortlist_candidates("banana_peel", [{"category": "drink"}]) == []
