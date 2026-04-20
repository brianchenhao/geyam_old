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
    """Billplz v3 webhook signing: sort keys, pipe-join as key1val1|key2val2|... then HMAC-SHA256."""
    keys_skip = {"x_signature"}
    payload = "|".join(f"{k}{form_fields[k]}" for k in sorted(form_fields.keys()) if k not in keys_skip)
    expected = hmac.new(xsign_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, x_signature)
