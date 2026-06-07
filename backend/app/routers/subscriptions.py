"""Stage 3 Phase 9 — Stripe-backed subscription billing.

Owner-facing endpoints:
  GET  /subscriptions/me           — current plan/status (used by Flutter banner)
  POST /subscriptions/checkout     — start a Checkout session to upgrade
  POST /subscriptions/portal       — open the Billing Portal to cancel / change card

Admin-facing endpoints (require_admin, @audited):
  POST /admin/subscriptions/{tenant_id}/cancel
  POST /admin/subscriptions/{tenant_id}/plan_change
  POST /admin/subscriptions/{tenant_id}/manual_extend

Webhook receiver (no auth, signature-verified):
  POST /subscriptions/webhook      — idempotent on event.id via processed_stripe_events

Tenant_id is propagated through Stripe via:
  - Customer.metadata.tenant_id (set on create_customer)
  - Subscription.metadata.tenant_id (set on create_checkout_session)
  - Checkout.Session.client_reference_id
So we can resolve a webhook event back to the local row without trusting the
customer record alone.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import stripe

from app import config
from app.database import SessionLocal
from app.deps import (
    bypass_tenant_scope, get_current_user, get_session, get_tenant,
    require_admin, require_role,
)
from app.models.processed_stripe_event import ProcessedStripeEvent
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.services import stripe_service
from app.services.audit import audited, write_audit_event

log = logging.getLogger(__name__)

router = APIRouter(tags=["subscriptions"])

VALID_PLANS = ("free", "pro", "business")
STRIPE_STATUS_TO_LOCAL = {
    # Stripe → local subscriptions.status (free-form within our CHECK constraint).
    "active": "active",
    "trialing": "active",
    "past_due": "past_due",
    "unpaid": "past_due",
    "incomplete": "past_due",
    "incomplete_expired": "canceled",
    "canceled": "canceled",
    "paused": "suspended",
}


# ----- helpers ---------------------------------------------------------------


async def _get_sub_for_tenant(session: AsyncSession, tenant_id: int) -> Subscription:
    sub = (await session.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )).scalars().first()
    if sub is None:
        # Backfill missed this tenant somehow — repair on read.
        sub = Subscription(tenant_id=tenant_id, plan="free", status="active")
        session.add(sub)
        await session.flush()
    return sub


def _sub_snapshot(sub: Subscription) -> dict[str, Any]:
    return {
        "tenant_id": sub.tenant_id,
        "plan": sub.plan,
        "status": sub.status,
        "stripe_customer_id": sub.stripe_customer_id,
        "stripe_subscription_id": sub.stripe_subscription_id,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
    }


# ----- owner-facing ----------------------------------------------------------


class SubscriptionOut(BaseModel):
    plan: str
    status: str
    current_period_end: Optional[datetime] = None
    past_due_since: Optional[datetime] = None
    suspended_at: Optional[datetime] = None
    has_stripe_customer: bool

    model_config = {"from_attributes": True}


@router.get("/subscriptions/me", dependencies=[Depends(require_role("owner"))])
async def my_subscription(
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> SubscriptionOut:
    sub = await _get_sub_for_tenant(session, tenant_id)
    await session.commit()
    return SubscriptionOut(
        plan=sub.plan, status=sub.status,
        current_period_end=sub.current_period_end,
        past_due_since=sub.past_due_since, suspended_at=sub.suspended_at,
        has_stripe_customer=bool(sub.stripe_customer_id),
    )


class CheckoutIn(BaseModel):
    plan: str  # "pro" or "business" — free is the default and has no Checkout


class CheckoutOut(BaseModel):
    checkout_url: str
    session_id: str


@router.post("/subscriptions/checkout", dependencies=[Depends(require_role("owner"))])
async def start_checkout(
    body: CheckoutIn,
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> CheckoutOut:
    if body.plan not in ("pro", "business"):
        raise HTTPException(status_code=400, detail="plan must be pro or business")

    sub = await _get_sub_for_tenant(session, tenant_id)
    async with bypass_tenant_scope():
        tenant = (await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalars().first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant missing")

    if not sub.stripe_customer_id:
        sub.stripe_customer_id = await stripe_service.create_customer(
            email=tenant.owner_email, tenant_id=tenant_id, name=tenant.name,
        )
        await session.commit()

    sess = await stripe_service.create_checkout_session(
        customer_id=sub.stripe_customer_id, plan=body.plan, tenant_id=tenant_id,
        success_url=config.STRIPE_CHECKOUT_SUCCESS_URL,
        cancel_url=config.STRIPE_CHECKOUT_CANCEL_URL,
    )
    return CheckoutOut(checkout_url=sess["url"], session_id=sess["id"])


class PortalOut(BaseModel):
    portal_url: str


@router.post("/subscriptions/portal", dependencies=[Depends(require_role("owner"))])
async def open_portal(
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> PortalOut:
    sub = await _get_sub_for_tenant(session, tenant_id)
    if not sub.stripe_customer_id:
        raise HTTPException(status_code=400, detail="no Stripe customer; upgrade via /subscriptions/checkout first")
    sess = await stripe_service.create_portal_session(
        customer_id=sub.stripe_customer_id,
        return_url=config.STRIPE_PORTAL_RETURN_URL,
    )
    return PortalOut(portal_url=sess["url"])


# ----- admin-facing (audited) ------------------------------------------------


async def _load_sub_for_audit(session: AsyncSession, kwargs: dict[str, Any]) -> Optional[dict[str, Any]]:
    """before-loader: snapshot the subscription row pre-mutation."""
    tid = kwargs.get("tenant_id")
    if not isinstance(tid, int):
        return None
    async with bypass_tenant_scope():
        sub = (await session.execute(
            select(Subscription).where(Subscription.tenant_id == tid)
        )).scalars().first()
    return _sub_snapshot(sub) if sub else None


class AdminCancelIn(BaseModel):
    at_period_end: bool = True


@router.post("/admin/subscriptions/{tenant_id}/cancel", dependencies=[Depends(require_admin)])
@audited("subscription.cancel", before=_load_sub_for_audit)
async def admin_cancel_subscription(
    tenant_id: int,
    body: AdminCancelIn,
    request: Request,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    async with bypass_tenant_scope():
        sub = (await session.execute(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        )).scalars().first()
        if sub is None or not sub.stripe_subscription_id:
            raise HTTPException(status_code=404, detail="no active stripe subscription")
        result = await stripe_service.cancel_subscription(
            subscription_id=sub.stripe_subscription_id, at_period_end=body.at_period_end,
        )
        # Local state updates land via webhook (customer.subscription.updated).
    return {"stripe": result, "tenant_id": tenant_id}


class AdminPlanChangeIn(BaseModel):
    plan: str  # "free" | "pro" | "business"


@router.post("/admin/subscriptions/{tenant_id}/plan_change", dependencies=[Depends(require_admin)])
@audited("subscription.plan_change", before=_load_sub_for_audit)
async def admin_plan_change(
    tenant_id: int,
    body: AdminPlanChangeIn,
    request: Request,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Admin-only forced plan change. Bypasses Checkout — for support / refund
    scenarios only. Does NOT touch Stripe; the local plan flag wins until the
    next webhook reconciles. Use sparingly."""
    if body.plan not in VALID_PLANS:
        raise HTTPException(status_code=400, detail=f"plan must be one of {VALID_PLANS}")
    async with bypass_tenant_scope():
        sub = (await session.execute(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        )).scalars().first()
        if sub is None:
            raise HTTPException(status_code=404, detail="subscription not found")
        tenant = (await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalars().first()
        sub.plan = body.plan
        if tenant is not None:
            tenant.plan = body.plan
        sub.updated_at = datetime.now(timezone.utc)
        await session.commit()
    return {"tenant_id": tenant_id, "plan": body.plan}


class AdminExtendIn(BaseModel):
    days: int  # extend current_period_end by N days


@router.post("/admin/subscriptions/{tenant_id}/manual_extend", dependencies=[Depends(require_admin)])
@audited("subscription.manual_extend", before=_load_sub_for_audit)
async def admin_manual_extend(
    tenant_id: int,
    body: AdminExtendIn,
    request: Request,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Push current_period_end forward without charging. Goodwill credit /
    on-call extension. Local-only (does NOT modify the Stripe subscription)."""
    if body.days <= 0 or body.days > 365:
        raise HTTPException(status_code=400, detail="days must be 1..365")
    async with bypass_tenant_scope():
        sub = (await session.execute(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        )).scalars().first()
        if sub is None:
            raise HTTPException(status_code=404, detail="subscription not found")
        anchor = sub.current_period_end or datetime.now(timezone.utc)
        sub.current_period_end = anchor + timedelta(days=body.days)
        # If they were past-due/suspended, the extension also reactivates.
        if sub.status in ("past_due", "suspended"):
            sub.status = "active"
            sub.past_due_since = None
            sub.suspended_at = None
            async with bypass_tenant_scope():
                tenant = (await session.execute(
                    select(Tenant).where(Tenant.id == tenant_id)
                )).scalars().first()
                if tenant is not None:
                    tenant.status = "active"
        sub.updated_at = datetime.now(timezone.utc)
        await session.commit()
    return {
        "tenant_id": tenant_id,
        "current_period_end": sub.current_period_end.isoformat(),
        "status": sub.status,
    }


# ----- webhook ---------------------------------------------------------------


def _plan_from_subscription_object(sub_obj: Any) -> Optional[str]:
    """Map a Stripe subscription object back to a local plan name by matching
    its price IDs against STRIPE_PRICE_PRO / STRIPE_PRICE_BUSINESS."""
    items = (sub_obj.get("items") or {}).get("data") or []
    for item in items:
        price_id = (item.get("price") or {}).get("id")
        if price_id and price_id == config.STRIPE_PRICE_PRO:
            return "pro"
        if price_id and price_id == config.STRIPE_PRICE_BUSINESS:
            return "business"
    return None


async def _resolve_tenant_id(session: AsyncSession, *, customer_id: Optional[str],
                              metadata: Optional[dict[str, Any]]) -> Optional[int]:
    """Prefer metadata.tenant_id (set by our checkout flow). Fall back to a
    customer_id lookup on the local subscriptions table."""
    if metadata and metadata.get("tenant_id"):
        try:
            return int(metadata["tenant_id"])
        except (TypeError, ValueError):
            pass
    if customer_id:
        async with bypass_tenant_scope():
            sub = (await session.execute(
                select(Subscription).where(Subscription.stripe_customer_id == customer_id)
            )).scalars().first()
        if sub is not None:
            return sub.tenant_id
    return None


async def _apply_subscription_event(session: AsyncSession, sub_obj: dict[str, Any]) -> dict[str, Any]:
    """Reconcile a local Subscription row from a Stripe subscription object.
    Used for customer.subscription.created / .updated / .deleted."""
    customer_id = sub_obj.get("customer")
    metadata = sub_obj.get("metadata") or {}
    tenant_id = await _resolve_tenant_id(session, customer_id=customer_id, metadata=metadata)
    if tenant_id is None:
        log.warning("stripe webhook: cannot resolve tenant for subscription %s", sub_obj.get("id"))
        return {"skipped": True, "reason": "unresolved_tenant"}

    async with bypass_tenant_scope():
        sub = (await session.execute(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        )).scalars().first()
        if sub is None:
            sub = Subscription(tenant_id=tenant_id, plan="free", status="active")
            session.add(sub)
            await session.flush()

        sub.stripe_customer_id = customer_id or sub.stripe_customer_id
        sub.stripe_subscription_id = sub_obj.get("id")
        plan = _plan_from_subscription_object(sub_obj)
        if plan:
            sub.plan = plan
        stripe_status = sub_obj.get("status", "")
        local_status = STRIPE_STATUS_TO_LOCAL.get(stripe_status, sub.status)
        sub.status = local_status

        cpe = sub_obj.get("current_period_end")
        if isinstance(cpe, (int, float)):
            sub.current_period_end = datetime.fromtimestamp(cpe, tz=timezone.utc)

        now = datetime.now(timezone.utc)
        if local_status == "past_due" and sub.past_due_since is None:
            sub.past_due_since = now
        if local_status == "active":
            sub.past_due_since = None
            sub.suspended_at = None
        sub.updated_at = now

        # Mirror plan/status onto the tenant row (read-hot, used by quota checks).
        tenant = (await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalars().first()
        if tenant is not None:
            tenant.plan = sub.plan
            tenant.status = "suspended" if sub.status == "suspended" else "active"

    return {"tenant_id": tenant_id, "plan": sub.plan, "status": sub.status}


async def _apply_invoice_event(session: AsyncSession, invoice: dict[str, Any], event_type: str) -> dict[str, Any]:
    customer_id = invoice.get("customer")
    sub_id = invoice.get("subscription")
    metadata = invoice.get("subscription_details", {}).get("metadata") or invoice.get("metadata") or {}
    tenant_id = await _resolve_tenant_id(session, customer_id=customer_id, metadata=metadata)
    if tenant_id is None:
        log.warning("stripe webhook: cannot resolve tenant for invoice %s", invoice.get("id"))
        return {"skipped": True, "reason": "unresolved_tenant"}

    async with bypass_tenant_scope():
        sub = (await session.execute(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        )).scalars().first()
        if sub is None:
            return {"skipped": True, "reason": "no_local_subscription"}

        now = datetime.now(timezone.utc)
        if event_type == "invoice.payment_failed":
            sub.status = "past_due"
            if sub.past_due_since is None:
                sub.past_due_since = now
        elif event_type == "invoice.payment_succeeded":
            sub.status = "active"
            sub.past_due_since = None
            sub.suspended_at = None
            cpe = invoice.get("period_end") or invoice.get("lines", {}).get("data", [{}])[0].get("period", {}).get("end")
            if isinstance(cpe, (int, float)):
                sub.current_period_end = datetime.fromtimestamp(cpe, tz=timezone.utc)
            tenant = (await session.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            )).scalars().first()
            if tenant is not None:
                tenant.status = "active"
        sub.updated_at = now

        # Mirror past-due back onto tenant row for quota checks (still 'active'
        # at the tenant level — grace period applies; sweeper flips to suspended).
    return {"tenant_id": tenant_id, "status": sub.status}


@router.post("/subscriptions/webhook")
async def stripe_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Stripe → us. Body is RAW (must not be re-parsed before signature verify).
    Idempotent on event.id via the processed_stripe_events table; duplicates
    return 200 OK with {duplicate: true}."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe_service.construct_event(payload=payload, sig_header=sig_header)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="invalid signature")
    except stripe_service.StripeNotConfigured:
        raise HTTPException(status_code=503, detail="stripe webhook not configured")

    event_id = event["id"]
    event_type = event["type"]
    data_object = event["data"]["object"]

    # Idempotency + business logic must commit together: insert the dedup row,
    # flush to surface a uniqueness conflict NOW (= duplicate event), then run
    # the business logic in the same transaction. Failures roll back both,
    # leaving the event re-processable on Stripe's next retry.
    async with bypass_tenant_scope():
        session.add(ProcessedStripeEvent(event_id=event_id, event_type=event_type))
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            return {"received": True, "duplicate": True, "event_id": event_id}

    outcome: dict[str, Any] = {"handled": False}
    try:
        if event_type in ("customer.subscription.created",
                          "customer.subscription.updated",
                          "customer.subscription.deleted"):
            outcome = await _apply_subscription_event(session, data_object)
        elif event_type in ("invoice.payment_failed", "invoice.payment_succeeded"):
            outcome = await _apply_invoice_event(session, data_object, event_type)
        else:
            outcome = {"ignored": True, "event_type": event_type}
        await session.commit()
    except Exception:
        await session.rollback()
        log.exception("stripe webhook %s (%s) failed during apply", event_type, event_id)
        # Audit the failure on a fresh session so the rolled-back work session
        # doesn't swallow the trail. (Dedup row was rolled back too, so Stripe
        # will retry and we will get another chance.)
        async with SessionLocal() as audit_s:
            async with bypass_tenant_scope():
                await write_audit_event(
                    audit_s, actor_email="stripe.webhook", action=f"webhook.{event_type}",
                    tenant_id=outcome.get("tenant_id"), success=False,
                    after_data={"event_id": event_id, "error": "apply_failed"},
                )
                await audit_s.commit()
        raise HTTPException(status_code=500, detail="webhook apply failed")

    # Audit trail of the webhook itself — actor=stripe.webhook so the admin
    # tile can show "what did Stripe just do?". Separate session so this insert
    # doesn't reopen the just-committed business txn.
    async with SessionLocal() as audit_s:
        async with bypass_tenant_scope():
            await write_audit_event(
                audit_s, actor_email="stripe.webhook", action=f"webhook.{event_type}",
                tenant_id=outcome.get("tenant_id"), success=True,
                after_data={"event_id": event_id, **outcome},
            )
            await audit_s.commit()

    return {"received": True, "event_id": event_id, "outcome": outcome}
