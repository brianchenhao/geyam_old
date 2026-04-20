"""Perceptual-hash helpers for OpenAI result caching (Phase 7)."""
import io

from PIL import Image


def compute(image_bytes: bytes) -> str:
    """8x8 average-hash (aHash) — 64-bit hex.
    Simpler than DCT pHash, robust enough for 'is this the same tray photo'
    deduplication which is all we need for the OpenAI cache."""
    import numpy as np

    img = Image.open(io.BytesIO(image_bytes)).convert("L").resize((8, 8))
    arr = np.array(img, dtype=float)
    avg = arr.mean()
    bits = "".join("1" if v > avg else "0" for v in arr.flatten())
    return f"{int(bits, 2):016x}"
