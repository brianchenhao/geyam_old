"""Chenki-backed owner-side analytics assistant for POST /ask.

Replaces the Stage 2 Ollama tool-calling chat (`ollama_chat.py`). Chenki
v0.1.0's `ChenkiClient.achat()` does not expose OpenAI-style `tools=`, so
this module classifies the question with a deterministic keyword matcher,
runs the picked tool from `assistant_tools.TOOLS`, then asks chenki to
paraphrase the JSON result in plain English.

One LLM call per question (vs. Ollama's potentially multi-round loop) —
faster, cheaper, no risk of malformed tool-call JSON.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from chenki import ChenkiClient, ChenkiConfig, Message

from app.services.assistant_tools import dispatch

log = logging.getLogger(__name__)

_client = ChenkiClient(config=ChenkiConfig(timeout=30, max_retries=1))


_SYSTEM_WITH_DATA = (
    "You are GEYAM POS's analytics assistant. Answer the owner's question in "
    "1-3 short sentences using ONLY the JSON data provided. Use Malaysian "
    "Ringgit (RM) for money. If the data shows zero / empty / null values, "
    "say so plainly (\"No items are low on stock right now.\"). Never invent "
    "numbers, item names, or staff names — only paraphrase what is in the "
    "data. Skip JSON keys; write natural sentences."
)

_SYSTEM_NO_DATA = (
    "You are GEYAM POS's analytics assistant. The owner asked a question "
    "that doesn't map to any of our analytics tools (sales, revenue, staff, "
    "stock, forecast, detection mix, recent / old transactions). Either "
    "answer briefly from general knowledge (1-2 sentences) or list the "
    "kinds of questions you CAN answer. Keep it short."
)


# Pattern order matters: more specific patterns first.
# "reorder point" routes to low_stock (specific config field), but bare
# "reorder" / "what should I reorder" routes to forecast — the negative
# lookahead `reorder(?!\W*point)` keeps the two from colliding.
_CLASSIFIERS: list[tuple[re.Pattern[str], str]] = [
    # Forecast / reorder planning — must beat "low_stock" for "what to reorder"
    (re.compile(
        r"\b(forecast|predicted? demand|purchase.?order|"
        r"(what|which)( items?)? (to|should I) (buy|order|reorder)|"
        r"reorder.?planning|"
        r"reorder(?!\W*point))\b",
        re.I,
    ), "forecast_reorder"),
    # Low stock / restock alerts
    (re.compile(
        r"\b(low.?stock|running.?low|stock.?alerts?|restock|reorder.?point|out of stock)\b",
        re.I,
    ), "low_stock_items"),
    # Staff performance
    (re.compile(
        r"\b(cashier|staff|employee|who (sold|performed|handled)|top.?staff)\b",
        re.I,
    ), "staff_performance"),
    # Detection mix
    (re.compile(
        r"\b(yolo|openai|mediapipe|detection|accuracy|model.* (doing|performance|mix))\b",
        re.I,
    ), "detection_source_mix"),
    # Recent transactions — allows "last 10 transactions" / "latest 5 sales"
    (re.compile(
        r"\b(last(?:\s+\d+)?\s+(transactions?|sales?|orders?)|"
        r"latest(?:\s+\d+)?\s+(transactions?|sales?|orders?)|"
        r"most recent|just sold|"
        r"recent (orders?|transactions?|sales?))\b",
        re.I,
    ), "recent_transactions"),
    # Old transactions
    (re.compile(
        r"\b(old (transactions?|orders?)|stale|history|older than|transactions? before)\b",
        re.I,
    ), "old_transactions"),
    # Revenue / day-by-day
    (re.compile(
        r"\b(revenue|total sales|how much .* (make|earn|made)|busiest day|quietest day|zero.?sales|average daily|takings|takeings)\b",
        re.I,
    ), "day_by_day_revenue_summary"),
    # Products / units (last because it's the broadest catch-all)
    (re.compile(
        r"\b(product|item|sku|best.?seller|units? sold|how (are|is) (products|items|sales)|revenue per)\b",
        re.I,
    ), "product_sales_summary"),
]


_DAYS_RE = re.compile(r"\b(\d+)\s*days?\b", re.I)
_LIMIT_RE = re.compile(r"\b(last|latest|recent|top)\s+(\d+)\b", re.I)

_DAYS_AWARE = {
    "product_sales_summary",
    "day_by_day_revenue_summary",
    "staff_performance",
    "detection_source_mix",
}


def classify(question: str) -> tuple[str | None, dict[str, Any]]:
    """Pick a tool by keyword match and lift simple int args from the question.

    Returns (tool_name_or_None, args_dict). Args are empty {} if nothing
    quantitative was mentioned — the tool falls back to its defaults.
    """
    for pattern, tool in _CLASSIFIERS:
        if pattern.search(question):
            args: dict[str, Any] = {}
            days_m = _DAYS_RE.search(question)
            if days_m and tool in _DAYS_AWARE:
                args["days"] = int(days_m.group(1))
            if tool == "old_transactions" and days_m:
                args["older_than_days"] = int(days_m.group(1))
            if tool == "recent_transactions":
                limit_m = _LIMIT_RE.search(question)
                if limit_m:
                    args["limit"] = int(limit_m.group(2))
            return tool, args
    return None, {}


async def ask_owner(question: str, session: AsyncSession) -> dict:
    """Owner analytics Q&A via chenki.

    Returns {"answer": str, "tools_used": list[str]}.
    """
    tool, args = classify(question)

    if tool is None:
        messages = [
            Message(role="system", content=_SYSTEM_NO_DATA),
            Message(role="user", content=question),
        ]
        try:
            result = await _client.achat(messages)
            return {"answer": result.text, "tools_used": []}
        except Exception as e:
            log.warning("chenki ask_owner (no tool) failed: %s", e)
            return {"answer": f"(LLM error: {type(e).__name__})", "tools_used": []}

    data = await dispatch(tool, args, session)

    messages = [
        Message(role="system", content=_SYSTEM_WITH_DATA),
        Message(
            role="user",
            content=(
                f"Question: {question}\n\n"
                f"Tool: {tool}\n"
                f"Data (JSON):\n{json.dumps(data, default=str)}"
            ),
        ),
    ]
    try:
        result = await _client.achat(messages)
        return {"answer": result.text, "tools_used": [tool]}
    except Exception as e:
        log.warning("chenki ask_owner (tool=%s) failed: %s", tool, e)
        return {"answer": f"(LLM error: {type(e).__name__})", "tools_used": [tool]}
