"""Webhook endpoint for Healthchecks.io alert escalation.

Healthchecks.io can call any URL on check failure/recovery. This endpoint
authenticates the call with a shared secret in the path segment (the only
auth shape Healthchecks supports without custom headers on the free tier),
then fans the alert out to Telegram + email via services/alerts.

Setup:
1. Set ALERTS_WEBHOOK_SECRET in .env.production (a 32+ char random string).
2. In Healthchecks → Integrations → Webhooks, create a "down" webhook:
     URL:    https://api.geyam.com/alerts/webhook/<secret>
     Method: POST
     Body:   {"name": "$NAME", "status": "$STATUS", "tags": "$TAGS"}
3. Add a paired "up" webhook with the same shape so recoveries also notify.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.services.alerts import dispatch

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("/webhook/{secret}")
async def healthchecks_webhook(secret: str, request: Request) -> dict[str, Any]:
    expected = os.getenv("ALERTS_WEBHOOK_SECRET", "")
    if not expected:
        # Fail closed: never accept webhook traffic without a configured secret.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="webhook not configured")
    if secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="bad secret")

    try:
        payload = await request.json()
    except Exception:
        payload = {}
    name = str(payload.get("name") or "unknown check")
    chk_status = str(payload.get("status") or "?")
    tags = str(payload.get("tags") or "")

    subject = f"[geyam] healthchecks: {name} → {chk_status}"
    body = f"check: {name}\nstatus: {chk_status}\ntags: {tags}"
    results = dispatch(subject=subject, body=body)
    return {"dispatched": True, "results": results}


@router.post("/test")
async def fire_test_alert(request: Request) -> dict[str, Any]:
    """Manual smoke test. Same secret-in-path auth as the webhook."""
    secret = request.headers.get("x-alert-secret", "")
    expected = os.getenv("ALERTS_WEBHOOK_SECRET", "")
    if not expected or secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="bad secret")
    results = dispatch(
        subject="[geyam] alert test",
        body="If you see this on Telegram and email, the alert pipeline works.",
    )
    return {"dispatched": True, "results": results}
