"""Chenki-llm wrapper for cashier-facing menu Q&A.

Backs POST /menu/ask. Targets Qwen 2.5 1.5B on brianchenhao-chenki-llm.hf.space
with a 30s timeout and one retry. Tenant scoping is enforced at the route
layer by loading only this tenant's active menu items before calling.
"""
from __future__ import annotations

import logging
from typing import Any

from chenki import ChenkiClient, ChenkiConfig
from chenki.prompts import RestaurantPrompts

log = logging.getLogger(__name__)

_client = ChenkiClient(config=ChenkiConfig(timeout=30, max_retries=1))


async def ask_menu(question: str, menu: list[dict[str, Any]]) -> str:
    messages = RestaurantPrompts.menu_qa(question, menu)
    result = await _client.achat(messages)
    return result.text


async def warmup() -> bool:
    """Fire one minimal Chenki call to wake the HF Space at deploy time.

    HF Spaces sleep after ~48h idle; the first /menu/ask after sleep eats a
    30-60s cold start. Calling this from FastAPI startup lets the deploy step
    absorb the wake delay so the first real user request is warm.

    Never raises. Returns True on success, False otherwise — startup must not
    block on a sleeping Space.
    """
    try:
        await ask_menu("warmup ping", [])
        log.info("chenki warmup succeeded")
        return True
    except Exception as e:
        log.warning("chenki warmup failed: %s", e)
        return False
