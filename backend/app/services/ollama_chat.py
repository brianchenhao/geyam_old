"""Ollama tool-calling chat wrapper for the POS assistant.

Uses /api/chat (not /api/generate) because it natively supports `tools=`
in OpenAI-compatible format. Targets Qwen3.5 (2B/4B) which is trained
for function calling.

Flow:
  1. Send [system, user] + tools.
  2. If reply has tool_calls, execute each, append results, loop.
  3. Stop when reply has content but no tool_calls, or loop cap hit.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.assistant_tools import TOOL_SCHEMAS, dispatch

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:2b")
MAX_TOOL_ROUNDS = 4
REQUEST_TIMEOUT = 90


SYSTEM_PROMPT = """You are GEYAM POS's in-app analytics assistant.

Role: you help the shop owner (not cashiers) understand their store's \
operations — sales, staff, stock, detection quality, and historical data — \
by calling one of the provided tools and paraphrasing the result in plain \
English (Malaysian Ringgit, RM).

## How to choose a tool

Always pick exactly ONE tool per question unless the user clearly asks \
two separate things. Match the user's intent to the tool:

- Products, items, SKUs, best-seller, units sold, which product makes the \
  most money  ->  product_sales_summary
- Revenue, total sales, average daily sales, busiest day, quietest day, \
  zero-sales days, how much did we make  ->  day_by_day_revenue_summary
- Cashiers, staff, who performed best, transaction count per person  \
  ->  staff_performance
- Low stock, running out, stock alert, what to restock right now  \
  ->  low_stock_items
- Forecast, predicted demand, reorder planning, what to buy from supplier, \
  purchase order suggestion  ->  forecast_reorder
- YOLO accuracy, OpenAI fallback usage, MediaPipe, detection quality, \
  how is the ML doing, detection mix  ->  detection_source_mix
- Last/latest/most recent transaction, what just sold, recent orders  \
  ->  recent_transactions
- Old transactions, stale orders, history before X days, transactions older \
  than a week  ->  old_transactions

## Rules

1. If the question maps to a tool, CALL the tool. Do not guess numbers.
2. If the user asks about a number of days (e.g. "last 30 days"), pass \
   `days` as that integer. Default is 7 when unspecified.
3. If the question does NOT map to any tool (e.g. chit-chat, setup help, \
   product pricing advice), answer briefly from general knowledge without \
   a tool call.
4. After a tool returns, write a SHORT plain-English summary (1-3 sentences). \
   Include specific numbers from the tool result. Use RM for money.
5. Do not invent items, staff, or dates. Only use what the tool returned.
6. If a tool returns an empty list or zero counts, say so plainly \
   ("No items are low on stock right now.").

## Example user questions that map to each tool

- product_sales_summary: "how are products selling?", "what's my best seller \
  this week?", "total units this month?", "revenue per product on average?"
- day_by_day_revenue_summary: "how was revenue last 7 days?", "what was my \
  best day?", "any zero-sales days this month?", "average daily takings?"
- staff_performance: "who's my top cashier?", "how is Aisha doing?", \
  "staff performance this week", "which staff handled the most orders?"
- low_stock_items: "what's running low?", "any stock alerts?", "which items \
  need restocking?", "show me low stock"
- forecast_reorder: "what should I reorder?", "predicted demand for next \
  week?", "purchase order suggestions", "reorder points"
- detection_source_mix: "how is YOLO doing?", "am I using OpenAI a lot?", \
  "detection accuracy mix", "did the model detect items reliably?"
- recent_transactions: "what was the last transaction?", "show me the latest \
  sale", "most recent orders", "what just sold?"
- old_transactions: "any transactions older than a week?", "how many stale \
  orders?", "transactions before last Monday", "old pending transactions"
"""


async def chat_with_tools(user_question: str, session: AsyncSession,
                           *, model: str | None = None) -> dict:
    """Run a tool-calling conversation and return the final answer.

    Returns: {"answer": str, "tool_calls": [{"name": str, "args": dict, "result": any}]}
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_question},
    ]
    tool_trace: list[dict] = []
    model_name = model or OLLAMA_MODEL

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for _ in range(MAX_TOOL_ROUNDS):
            try:
                r = await client.post(
                    f"{OLLAMA_HOST}/api/chat",
                    json={
                        "model": model_name,
                        "messages": messages,
                        "tools": TOOL_SCHEMAS,
                        "stream": False,
                        "options": {"temperature": 0.1},
                    },
                )
                if r.status_code == 404:
                    return {
                        "answer": f"(Model '{model_name}' is not pulled on the Ollama host. Run: `ollama pull {model_name}` and try again.)",
                        "tool_calls": tool_trace,
                    }
                if r.status_code >= 400:
                    body = r.text[:300]
                    return {
                        "answer": f"(Ollama returned HTTP {r.status_code}: {body})",
                        "tool_calls": tool_trace,
                    }
                data = r.json()
            except httpx.ConnectError:
                return {
                    "answer": f"(Cannot reach Ollama at {OLLAMA_HOST}. Is the Ollama server running?)",
                    "tool_calls": tool_trace,
                }
            except Exception as e:
                return {
                    "answer": f"(LLM error: {type(e).__name__}: {e})",
                    "tool_calls": tool_trace,
                }

            msg = data.get("message") or {}
            content = (msg.get("content") or "").strip()
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                return {"answer": content or "(no answer)", "tool_calls": tool_trace}

            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                fn = (tc.get("function") or {})
                name = fn.get("name", "")
                raw_args = fn.get("arguments", {})
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args) if raw_args.strip() else {}
                    except json.JSONDecodeError:
                        args = {}
                else:
                    args = raw_args or {}

                result = await dispatch(name, args, session)
                tool_trace.append({"name": name, "args": args, "result": result})
                messages.append({
                    "role": "tool",
                    "name": name,
                    "content": json.dumps(result, default=str),
                })

    return {
        "answer": "(The assistant used too many tool calls without finishing. Try rephrasing your question.)",
        "tool_calls": tool_trace,
    }
