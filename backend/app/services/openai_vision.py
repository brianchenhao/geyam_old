"""OpenAI GPT-4o vision fallback for /detect.

Used when YOLO returns an implausible count (e.g. >3 of the same item on
one tray). Takes raw image bytes + the store's menu, asks GPT-4o to name
what's visible constrained to the menu, and returns a list of
(label, qty, confidence) tuples the detect router can turn into the
normal detections response shape.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from typing import Sequence

from openai import AsyncOpenAI, OpenAIError

logger = logging.getLogger(__name__)

OPENAI_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "60"))


class VisionError(Exception):
    """Raised when the vision fallback cannot produce usable detections."""


def _client() -> AsyncOpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise VisionError("OPENAI_API_KEY is not set")
    return AsyncOpenAI(api_key=key, timeout=OPENAI_TIMEOUT)


def _build_prompt(menu_labels: Sequence[str]) -> str:
    menu_list = ", ".join(sorted(menu_labels)) if menu_labels else "(no items)"
    return (
        "Identify the packaged food items on this tray. "
        f"Only identify items from this menu: {menu_list}. "
        "Return item names and quantities. "
        "Respond in strict JSON with the shape "
        '{"items": [{"label": "<one of the menu labels>", "quantity": <int>}]}. '
        "Use the exact label strings from the menu. "
        "If nothing from the menu is visible, return {\"items\": []}."
    )


async def detect_with_vision(
    image_bytes: bytes,
    menu_labels: Sequence[str],
    content_type: str = "image/jpeg",
) -> list[dict]:
    """Run GPT-4o vision, return a list of {label, quantity, confidence}.

    Raises VisionError on any failure the router should report upstream.
    """
    if not image_bytes:
        raise VisionError("empty image bytes")

    client = _client()
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{content_type};base64,{b64}"
    prompt = _build_prompt(menu_labels)

    try:
        resp = await client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
        )
    except OpenAIError as e:
        logger.exception("OpenAI vision call failed")
        raise VisionError(f"openai call failed: {e}") from e

    content = (resp.choices[0].message.content or "").strip()
    if not content:
        raise VisionError("empty response from vision model")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise VisionError(f"invalid JSON from vision model: {e}") from e

    raw_items = parsed.get("items")
    if not isinstance(raw_items, list):
        raise VisionError("response missing 'items' array")

    allowed = set(menu_labels)
    out: list[dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        qty = item.get("quantity")
        if not isinstance(label, str) or label not in allowed:
            continue
        try:
            qty_int = int(qty)
        except (TypeError, ValueError):
            continue
        if qty_int <= 0:
            continue
        out.append(
            {
                "label": label,
                "quantity": qty_int,
                "confidence": 0.9,
            }
        )
    return out
