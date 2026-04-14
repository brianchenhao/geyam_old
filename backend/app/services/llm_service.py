"""Ollama chat client + sales-context builder."""
import os

import httpx

from app.services.forecast import compute_forecast

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:latest")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "120"))

SYSTEM_PROMPT = (
    "You are a sales analyst for a packaged food store called GEYAM. "
    "Answer questions based on the sales data provided. Be concise."
)


async def _build_sales_context() -> str:
    forecast = await compute_forecast()
    if not forecast:
        return "No products or sales data available yet."
    lines = [f"Recent sales (last {forecast[0]['days_analyzed']} days):"]
    for f in forecast:
        note = f" [{f['note']}]" if f["note"] else ""
        lines.append(
            f"- {f['name']}: {f['total_sold']} units sold, "
            f"avg {f['avg_daily_sales']}/day, "
            f"next-week forecast {f['predicted_next_week']} units, "
            f"trend {f['trend']}{note}"
        )
    return "\n".join(lines)


async def ask_llm(question: str) -> dict:
    context = await _build_sales_context()
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"{context}\n\n"
        f"Question: {question}\n\n"
        f"Answer:"
    )
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                },
            )
    except httpx.ConnectError:
        return {
            "error": (
                f"Ollama not reachable at {OLLAMA_URL}. "
                f"Make sure Ollama is running and pull a model: "
                f"`ollama pull {OLLAMA_MODEL}`"
            )
        }
    except httpx.ReadTimeout:
        return {"error": f"LLM request timed out after {OLLAMA_TIMEOUT}s"}

    if resp.status_code != 200:
        return {
            "error": f"Ollama returned HTTP {resp.status_code}: {resp.text[:300]}"
        }

    data = resp.json()
    answer = (data.get("response") or "").strip()
    return {
        "answer": answer,
        "model": OLLAMA_MODEL,
        "context": context,
    }
