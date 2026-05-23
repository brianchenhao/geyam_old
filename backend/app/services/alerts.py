"""Alert dispatcher — Telegram + email.

Used by:
- the Healthchecks.io webhook receiver (`routers/alerts.py`) on check failures,
- backend code that wants to escalate (e.g. webhook handler errors, backup failures).

Both channels are best-effort: a failure in one does not stop the other, and
neither raises. Callers get back a `dict[channel, str]` with per-channel result
strings so failures show up in logs without breaking the calling code path.

Env vars:
- TELEGRAM_BOT_TOKEN      bot token from @BotFather
- TELEGRAM_ALERT_CHAT_ID  chat id to receive alerts (numeric, can be negative for groups)
- ALERT_EMAIL_TO          comma-separated recipients (falls back to ADMIN_EMAILS)
- RESEND_API_KEY          existing Resend key (reused for alerts)
"""
from __future__ import annotations

import os
from typing import Iterable

import httpx

from app.config import ADMIN_EMAILS, RESEND_API_KEY, RESEND_FROM

TELEGRAM_API = "https://api.telegram.org"
HTTP_TIMEOUT_S = 5.0


def _alert_recipients() -> list[str]:
    raw = os.getenv("ALERT_EMAIL_TO", "").strip()
    if raw:
        return [e.strip() for e in raw.split(",") if e.strip()]
    return list(ADMIN_EMAILS)


def send_telegram(text: str) -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_ALERT_CHAT_ID", "")
    if not token or not chat_id:
        return "skipped:no-creds"
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    try:
        r = httpx.post(
            url,
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=HTTP_TIMEOUT_S,
        )
        if r.status_code == 200:
            return "ok"
        return f"http:{r.status_code}"
    except Exception as e:
        return f"error:{type(e).__name__}"


def send_email(*, subject: str, text: str, to: Iterable[str] | None = None) -> str:
    if not RESEND_API_KEY:
        return "skipped:no-key"
    recipients = list(to) if to else _alert_recipients()
    if not recipients:
        return "skipped:no-recipients"
    try:
        import resend
        resend.api_key = RESEND_API_KEY
        resp = resend.Emails.send({
            "from": RESEND_FROM,
            "to": recipients,
            "subject": subject,
            "text": text,
        })
        if isinstance(resp, dict):
            mid = resp.get("id") or resp.get("data", {}).get("id")
            if mid:
                return f"ok:{mid}"
        return "ok"
    except Exception as e:
        return f"error:{type(e).__name__}"


def dispatch(*, subject: str, body: str) -> dict[str, str]:
    """Fan out to both channels. Telegram gets subject+body inline; email gets them split."""
    text = f"{subject}\n\n{body}" if body else subject
    return {
        "telegram": send_telegram(text),
        "email": send_email(subject=subject, text=body or subject),
    }
