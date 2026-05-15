"""Minimal per-tenant Billplz v3 client."""
import hashlib
import hmac
from typing import Any, Optional
from urllib.parse import urlencode

import httpx


SANDBOX_BASE = "https://www.billplz-sandbox.com/api/v3"
PRODUCTION_BASE = "https://www.billplz.com/api/v3"


def _base(mode: str) -> str:
    return PRODUCTION_BASE if mode == "production" else SANDBOX_BASE


def create_bill(
    *,
    mode: str,
    api_key: str,
    collection_id: str,
    name: str,
    email: str,
    amount_cents: int,
    description: str,
    callback_url: str,
    redirect_url: str,
    reference_1: Optional[str] = None,
    reference_2: Optional[str] = None,
) -> dict[str, Any]:
    url = f"{_base(mode)}/bills"
    payload = {
        "collection_id": collection_id,
        "email": email,
        "name": name,
        "amount": amount_cents,
        "description": description,
        "callback_url": callback_url,
        "redirect_url": redirect_url,
    }
    if reference_1:
        payload["reference_1"] = str(reference_1)
    if reference_2:
        payload["reference_2"] = str(reference_2)
    r = httpx.post(url, auth=(api_key, ""), data=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_bill(*, mode: str, api_key: str, bill_id: str) -> dict[str, Any]:
    url = f"{_base(mode)}/bills/{bill_id}"
    r = httpx.get(url, auth=(api_key, ""), timeout=10)
    r.raise_for_status()
    return r.json()


def verify_webhook_signature(*, xsign_key: str, form_fields: dict[str, str], x_signature: str) -> bool:
    """Billplz v3 webhook X-Signature (per jomweb/billplz Signature::WEBHOOK_PARAMETERS):
    fixed field order, pipe-joined as key1val1|key2val2|..., HMAC-SHA256 with key as string.
    Required fields contribute even when missing (empty value); optional ones only if present."""
    webhook_order = [
        "amount", "collection_id", "due_at", "email", "id", "mobile", "name",
        "paid_amount", "paid_at", "paid", "state", "transaction_id", "transaction_status", "url",
    ]
    required = {
        "amount", "collection_id", "due_at", "email", "id", "mobile", "name",
        "paid_amount", "paid_at", "paid", "state", "url",
    }
    parts = []
    for attr in webhook_order:
        if attr in form_fields or attr in required:
            parts.append(f"{attr}{form_fields.get(attr, '')}")
    payload = "|".join(parts).encode()
    expected = hmac.new(xsign_key.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, x_signature)
