"""Thin wrapper around the ``stripe`` SDK.

Goals:
  - Module import never fails if STRIPE_API_KEY is unset (tests + CI can
    import this without secrets). API key is set lazily on first call.
  - All network calls run in a threadpool — the SDK is synchronous and we are
    inside async FastAPI handlers.
  - Surface only the ~5 calls the rest of the app needs so the SDK isn't leaked
    into routers.

Plan IDs come from STRIPE_PRICE_PRO / STRIPE_PRICE_BUSINESS env vars; "free" is
not a Stripe price (it's the absence of a subscription, recorded locally in
``subscriptions`` with plan='free').
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import stripe

from app import config

log = logging.getLogger(__name__)


class StripeNotConfigured(RuntimeError):
    """Raised when a Stripe API call is made but no API key is configured."""


def _ensure_key() -> None:
    if not config.STRIPE_API_KEY:
        raise StripeNotConfigured(
            "STRIPE_API_KEY is not set. Either set it in the env or skip the "
            "/subscriptions endpoints during local dev."
        )
    # Re-read each call so a test or runbook step that changes the env between
    # calls (e.g. test → live cutover dry-run) takes effect immediately.
    stripe.api_key = config.STRIPE_API_KEY


def price_id_for_plan(plan: str) -> str:
    if plan == "pro":
        return config.STRIPE_PRICE_PRO
    if plan == "business":
        return config.STRIPE_PRICE_BUSINESS
    raise ValueError(f"no Stripe price id for plan {plan!r} (free has no price)")


async def create_customer(*, email: str, tenant_id: int, name: Optional[str] = None) -> str:
    """Create a Stripe Customer. ``tenant_id`` is stored in metadata so webhook
    events can be routed back to the right local row."""
    _ensure_key()

    def _do() -> str:
        cust = stripe.Customer.create(
            email=email,
            name=name,
            metadata={"tenant_id": str(tenant_id), "source": "geyam"},
        )
        return cust["id"]

    return await asyncio.to_thread(_do)


async def create_checkout_session(
    *, customer_id: str, plan: str, tenant_id: int,
    success_url: str, cancel_url: str,
) -> dict[str, Any]:
    """Stripe-hosted Checkout for new subscriptions. Returns {id, url}."""
    _ensure_key()
    price_id = price_id_for_plan(plan)

    def _do() -> dict[str, Any]:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=str(tenant_id),
            subscription_data={"metadata": {"tenant_id": str(tenant_id), "plan": plan}},
            allow_promotion_codes=True,
        )
        return {"id": session["id"], "url": session["url"]}

    return await asyncio.to_thread(_do)


async def create_portal_session(*, customer_id: str, return_url: str) -> dict[str, Any]:
    """Stripe Billing Portal — cancel / change plan / update card."""
    _ensure_key()

    def _do() -> dict[str, Any]:
        sess = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return {"id": sess["id"], "url": sess["url"]}

    return await asyncio.to_thread(_do)


async def cancel_subscription(*, subscription_id: str, at_period_end: bool = True) -> dict[str, Any]:
    """Cancel a Stripe subscription. ``at_period_end=True`` lets the tenant
    keep service until current_period_end (the typical product behaviour)."""
    _ensure_key()

    def _do() -> dict[str, Any]:
        if at_period_end:
            sub = stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
        else:
            sub = stripe.Subscription.delete(subscription_id)
        return {
            "id": sub["id"],
            "status": sub["status"],
            "cancel_at_period_end": sub.get("cancel_at_period_end"),
            "canceled_at": sub.get("canceled_at"),
        }

    return await asyncio.to_thread(_do)


def construct_event(*, payload: bytes, sig_header: str) -> stripe.Event:
    """Verify the webhook signature and parse the event. Raises
    ``stripe.error.SignatureVerificationError`` on a bad signature."""
    if not config.STRIPE_WEBHOOK_SECRET:
        raise StripeNotConfigured("STRIPE_WEBHOOK_SECRET is not set")
    return stripe.Webhook.construct_event(
        payload=payload,
        sig_header=sig_header,
        secret=config.STRIPE_WEBHOOK_SECRET,
    )
