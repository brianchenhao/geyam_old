"""Phase 15 #91: Telegram bot skeleton for owner quick queries.

Polls Telegram for messages. Each chat.id must be pre-authorized by mapping it
to a tenant_handle in the TELEGRAM_OWNERS env var:
    TELEGRAM_OWNERS=123456789:brianchenjunhao,987654321:demo-shop

Supports three commands right now; extend as needed:
    /sales   → today's revenue + tx count
    /low     → low-stock count
    /ask X   → round-trips to the /ask LLM path

Run:
    TELEGRAM_BOT_TOKEN=... python scripts/telegram_bot.py
"""
import asyncio
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal, current_tenant_id  # noqa: E402
from app.models import MenuItem, Tenant, Transaction  # noqa: E402


def _auth_map() -> dict[int, str]:
    raw = os.getenv("TELEGRAM_OWNERS", "")
    out: dict[int, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if ":" in pair:
            cid, handle = pair.split(":", 1)
            try:
                out[int(cid)] = handle.strip()
            except ValueError:
                continue
    return out


async def _quick_kpi(handle: str) -> str:
    async with SessionLocal() as s:
        t = await s.scalar(select(Tenant).where(Tenant.handle == handle))
        if t is None:
            return f"(unknown tenant: {handle})"
        tok = current_tenant_id.set(t.id)
        try:
            today = date.today()
            start = datetime(today.year, today.month, today.day)
            rev = await s.scalar(
                select(func.coalesce(func.sum(Transaction.total), 0))
                .where(Transaction.status == "paid", Transaction.paid_at >= start)
            ) or Decimal("0")
            n = await s.scalar(
                select(func.count(Transaction.id))
                .where(Transaction.status == "paid", Transaction.paid_at >= start)
            ) or 0
        finally:
            current_tenant_id.reset(tok)
    return f"📊 Today — RM {rev} across {n} paid sales"


async def _low(handle: str) -> str:
    async with SessionLocal() as s:
        t = await s.scalar(select(Tenant).where(Tenant.handle == handle))
        if t is None:
            return "(unknown tenant)"
        tok = current_tenant_id.set(t.id)
        try:
            n = await s.scalar(
                select(func.count(MenuItem.id))
                .where(MenuItem.is_active == True,  # noqa: E712
                       MenuItem.stock_qty <= MenuItem.reorder_point)
            ) or 0
        finally:
            current_tenant_id.reset(tok)
    return f"📦 {n} item(s) at or below reorder point"


async def _handle_message(msg: dict, auth: dict[int, str]) -> str | None:
    text = msg.get("text") or ""
    chat_id = msg.get("chat", {}).get("id")
    handle = auth.get(chat_id)
    if handle is None:
        return f"You're not authorised (chat_id={chat_id}).\n" \
               f"Add '{chat_id}:<tenant_handle>' to TELEGRAM_OWNERS."
    if text.startswith("/sales"):
        return await _quick_kpi(handle)
    if text.startswith("/low"):
        return await _low(handle)
    if text.startswith("/ask "):
        question = text[5:].strip()
        if not question:
            return "Usage: /ask <question>"
        # Defer to the same Ollama path the /ask endpoint uses.
        from app.routers.dashboard import ask as _ask_route  # noqa: F401
        return "(/ask over Telegram not wired yet — use the web dashboard)"
    return "Commands: /sales · /low · /ask <question>"


async def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("! TELEGRAM_BOT_TOKEN not set")
        return
    auth = _auth_map()
    if not auth:
        print("! TELEGRAM_OWNERS empty — no chat ids will be authorised")
    base = f"https://api.telegram.org/bot{token}"
    offset = 0
    async with httpx.AsyncClient(timeout=60.0) as c:
        while True:
            try:
                r = await c.get(f"{base}/getUpdates",
                                params={"offset": offset, "timeout": 30})
                data = r.json()
            except Exception as e:
                print(f"poll error: {e}")
                await asyncio.sleep(5)
                continue
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message")
                if not msg:
                    continue
                reply = await _handle_message(msg, auth)
                if reply:
                    await c.post(f"{base}/sendMessage", json={
                        "chat_id": msg["chat"]["id"], "text": reply,
                    })


if __name__ == "__main__":
    asyncio.run(main())
