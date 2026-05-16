"""Chenki-llm wrapper for cashier-facing menu Q&A.

Backs POST /menu/ask. Targets Qwen 2.5 1.5B on brianchenhao-chenki-llm.hf.space
with a 30s timeout and one retry. Tenant scoping is enforced at the route
layer by loading only this tenant's active menu items before calling.
"""
from __future__ import annotations

from typing import Any

from chenki import ChenkiClient, ChenkiConfig
from chenki.prompts import RestaurantPrompts

_client = ChenkiClient(config=ChenkiConfig(timeout=30, max_retries=1))


async def ask_menu(question: str, menu: list[dict[str, Any]]) -> str:
    messages = RestaurantPrompts.menu_qa(question, menu)
    result = await _client.achat(messages)
    return result.text
