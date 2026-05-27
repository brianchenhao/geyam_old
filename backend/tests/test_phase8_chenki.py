"""Phase 8 — Chenki integration tests.

Most checks are fast unit tests (singleton sanity + the owner-side
keyword classifier in chenki_assistant). The two LLM round-trip tests
are gated on LIVE_TESTS=1, because:
  - they need internet,
  - the HF Space can be cold (30-60s first request),
  - CI shouldn't pay LLM cost on every run.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.services import chenki_menu_ask
from app.services.chenki_assistant import classify
from app.services.chenki_menu_ask import ask_menu, warmup

skip_unless_live = pytest.mark.skipif(
    not os.environ.get("LIVE_TESTS"),
    reason="set LIVE_TESTS=1 to hit the live chenki-llm HF Space",
)


# ---------- chenki_menu_ask (cashier /menu/ask) ----------

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


# ---------- chenki_assistant.classify (owner /ask) ----------

@pytest.mark.parametrize("question,expected_tool", [
    ("how are products selling?", "product_sales_summary"),
    ("what's my best seller this week?", "product_sales_summary"),
    ("total units sold last month", "product_sales_summary"),
    ("how was revenue last 7 days?", "day_by_day_revenue_summary"),
    ("what was my busiest day?", "day_by_day_revenue_summary"),
    ("any zero sales days?", "day_by_day_revenue_summary"),
    ("who is my top cashier?", "staff_performance"),
    ("which staff handled the most orders?", "staff_performance"),
    # Note: "how is Aisha doing?" — naive keyword classifier can't recognize
    # staff names without a name list; falls through to no-tool chenki path
    # which will surface "I can answer about staff performance / stock / etc."
    ("what's running low?", "low_stock_items"),
    ("show me low stock", "low_stock_items"),
    ("any stock alerts right now?", "low_stock_items"),
    ("what should I reorder?", "forecast_reorder"),
    ("forecast demand for next week", "forecast_reorder"),
    ("purchase order suggestions please", "forecast_reorder"),
    ("how is YOLO doing?", "detection_source_mix"),
    ("am I using OpenAI a lot?", "detection_source_mix"),
    ("what was the last transaction?", "recent_transactions"),
    ("show me the most recent orders", "recent_transactions"),
    ("any transactions older than a week?", "old_transactions"),
    ("how many stale orders?", "old_transactions"),
])
def test_classify_routes_question_to_tool(question, expected_tool):
    tool, _args = classify(question)
    assert tool == expected_tool, f"{question!r} routed to {tool!r}, expected {expected_tool!r}"


def test_classify_returns_none_for_unrelated_question():
    """Off-topic questions fall through to the no-tool general path."""
    tool, args = classify("what's the weather today?")
    assert tool is None
    assert args == {}


def test_classify_extracts_days_argument():
    tool, args = classify("how was revenue last 14 days?")
    assert tool == "day_by_day_revenue_summary"
    assert args == {"days": 14}


def test_classify_extracts_older_than_for_old_transactions():
    tool, args = classify("transactions older than 30 days")
    assert tool == "old_transactions"
    assert args == {"older_than_days": 30}


def test_classify_extracts_limit_for_recent_transactions():
    tool, args = classify("show me the last 10 transactions")
    assert tool == "recent_transactions"
    assert args == {"limit": 10}


def test_classify_forecast_beats_low_stock_on_reorder_intent():
    """'what to reorder' must hit forecast_reorder, not low_stock_items —
    the ordering of _CLASSIFIERS is load-bearing for that disambiguation."""
    tool, _args = classify("what items should I reorder this week?")
    assert tool == "forecast_reorder"
