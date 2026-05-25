"""Phase 8 — Chenki integration tests.

The first two tests hit the real chenki-llm HF Space and are skipped unless
LIVE_TESTS=1, because:
  - they need internet,
  - the Space can be cold (30-60s first request),
  - CI shouldn't pay LLM cost on every run.

The third test (test_singleton_is_reused) is a fast unit check that runs
unconditionally.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.services import chenki_menu_ask
from app.services.chenki_menu_ask import ask_menu, warmup

skip_unless_live = pytest.mark.skipif(
    not os.environ.get("LIVE_TESTS"),
    reason="set LIVE_TESTS=1 to hit the live chenki-llm HF Space",
)


@skip_unless_live
@pytest.mark.asyncio
async def test_warmup_succeeds_even_when_cold():
    """warmup() must return True against a reachable Space, even on cold start.

    Plan §568 step 6: first /ask after 48h sleep succeeds. The warmup helper
    exists precisely so deploy absorbs that 30-60s delay instead of a user
    eating it on the first real request.
    """
    ok = await warmup()
    assert ok, "warmup() returned False — Space unreachable or chenki misconfigured"


@skip_unless_live
@pytest.mark.asyncio
async def test_ask_menu_returns_non_empty_answer():
    """ask_menu produces a non-empty string for a realistic prompt."""
    menu = [
        {"name": "Milo", "category": "drinks", "price": "3.50"},
        {"name": "Roti Bakar", "category": "snacks", "price": "2.80"},
    ]
    answer = await ask_menu("What drinks do you have?", menu)
    assert isinstance(answer, str)
    assert answer.strip(), "expected non-empty model reply"


def test_singleton_is_reused():
    """The module-level ChenkiClient must be a singleton — Phase 8 step 2."""
    first = chenki_menu_ask._client
    second = chenki_menu_ask._client
    assert first is second
