"""Image preprocessing shared by all detection stages."""
from io import BytesIO

import imagehash
from PIL import Image, ImageOps


def load_and_prep(raw: bytes) -> Image.Image:
    """Decode -> EXIF-rotate -> resize longest edge to 1280 -> RGB."""
    img = Image.open(BytesIO(raw))
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    img.thumbnail((1280, 1280))
    return img


def perceptual_hash(img: Image.Image) -> str:
    return str(imagehash.phash(img))
