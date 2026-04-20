"""Billplz v3 client — per-tenant creds, sandbox/prod URL switch, x-signature verify.

Docs: https://www.billplz.com/api
- Create bill:     POST /api/v3/bills    (HTTP Basic: api_key + '')
- Get bill:        GET  /api/v3/bills/{id}
- Webhook payload: form-encoded fields with an x_signature field
- x_signature is HMAC-SHA256 of
    '|'.join(f'{k}{v}' for k,v in sorted(params.items()) if k != 'x_signature')
  using the collection's x-signature key.
"""
import hashlib
import hmac
from typing import Any

import httpx

from app.models import TenantSettings
from app.services import crypto


class BillplzConfigError(Exception):
    pass


def _base_url(mode: str) -> str:
    return (
        "https://www.billplz-sandbox.com/api/v3"
        if mode == "sandbox" else "https://www.billplz.com/api/v3"
    )


def _require_creds(settings: TenantSettings) -> tuple[str, str, str, str]:
    api_key = crypto.decrypt(settings.billplz_api_key)
    xsign = crypto.decrypt(settings.billplz_xsign_key)
    col = settings.billplz_collection_id
    mode = settings.billplz_mode or "sandbox"
    if not (api_key and xsign and col):
        raise BillplzConfigError("billplz creds missing")
    return api_key, xsign, col, mode


async def create_bill(
    settings: TenantSettings,
    *,
    name: str,
    email: str | None,
    mobile: str | None,
    amount_sen: int,
    description: str,
    callback_url: str,
    redirect_url: str | None = None,
    reference_1_label: str | None = None,
    reference_1: str | None = None,
) -> dict[str, Any]:
    api_key, _xsign, col, mode = _require_creds(settings)
    payload: dict[str, Any] = {
        "collection_id": col,
        "description": description,
        "email": email or "",
        "mobile": mobile or "",
        "name": name,
        "amount": amount_sen,
        "callback_url": callback_url,
    }
    if redirect_url:
        payload["redirect_url"] = redirect_url
    if reference_1_label and reference_1:
        payload["reference_1_label"] = reference_1_label
        payload["reference_1"] = reference_1

    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(
            f"{_base_url(mode)}/bills", data=payload, auth=(api_key, "")
        )
    r.raise_for_status()
    return r.json()


async def get_bill(settings: TenantSettings, bill_id: str) -> dict[str, Any]:
    api_key, _xsign, _col, mode = _require_creds(settings)
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(f"{_base_url(mode)}/bills/{bill_id}", auth=(api_key, ""))
    r.raise_for_status()
    return r.json()


def verify_webhook(settings: TenantSettings, form: dict[str, str]) -> bool:
    xsign = crypto.decrypt(settings.billplz_xsign_key)
    if not xsign:
        return False
    sig = form.get("x_signature") or ""
    source = "|".join(
        f"{k}{v}" for k, v in sorted(form.items()) if k != "x_signature"
    )
    mac = hmac.new(xsign.encode(), source.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, sig)
