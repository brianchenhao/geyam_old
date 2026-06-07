"""Stage 3 Phase 9 — Stripe billing + admin audit log.

Run:
    docker compose exec backend pytest -xvs tests/test_stage3_phase9_stripe.py

Covers:
  - @audited writes a row on success AND on failure (audit-on-failure)
  - Admin audit router enforces ADMIN_EMAILS
  - Plan-quota gates raise 402 when over the cap
  - Suspended tenants get 423 on mutations (block via ensure_active)
  - Stripe webhook is idempotent on event.id (duplicate → 200 {duplicate: true})
  - Webhook updates the local subscription row
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app import config, tenant_context  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.deps import bypass_tenant_scope  # noqa: E402
from app.models.admin_audit_log import AdminAuditLog  # noqa: E402
from app.models.menu_item import MenuItem  # noqa: E402
from app.models.processed_stripe_event import ProcessedStripeEvent  # noqa: E402
from app.models.subscription import Subscription  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402
from app.security import issue_access_token, issue_admin_token  # noqa: E402
from app.services.audit import audited  # noqa: E402
from main import app  # noqa: E402

HANDLE = "p9stripe"
ADMIN_EMAIL = "admin@p9.test"


@pytest.fixture(autouse=True)
def _admin_in_whitelist():
    """Force ADMIN_EMAILS to include our test admin for the duration of one test
    without permanently mutating the module-level constant."""
    original_config = list(config.ADMIN_EMAILS)
    original_deps = None
    from app import deps as _deps
    if hasattr(_deps, "ADMIN_EMAILS"):
        original_deps = list(_deps.ADMIN_EMAILS)
        _deps.ADMIN_EMAILS = [ADMIN_EMAIL, *_deps.ADMIN_EMAILS]
    config.ADMIN_EMAILS = [ADMIN_EMAIL, *config.ADMIN_EMAILS]
    try:
        yield
    finally:
        config.ADMIN_EMAILS = original_config
        if original_deps is not None:
            _deps.ADMIN_EMAILS = original_deps


@pytest.fixture(autouse=True)
async def _dispose_engine_between_tests():
    yield
    await engine.dispose()


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _cleanup():
    tenant_context.set_current_tenant_id(None)
    async with SessionLocal() as s:
        async with bypass_tenant_scope():
            tids = (await s.execute(
                select(Tenant.id).where(Tenant.handle == HANDLE)
            )).scalars().all()
            if tids:
                await s.execute(delete(AdminAuditLog).where(AdminAuditLog.tenant_id.in_(tids)))
                await s.execute(delete(Subscription).where(Subscription.tenant_id.in_(tids)))
                await s.execute(delete(MenuItem).where(MenuItem.tenant_id.in_(tids)))
                await s.execute(delete(User).where(User.tenant_id.in_(tids)))
                await s.execute(delete(Tenant).where(Tenant.id.in_(tids)))
            await s.execute(delete(AdminAuditLog).where(AdminAuditLog.actor_email == ADMIN_EMAIL))
            await s.execute(delete(ProcessedStripeEvent).where(
                ProcessedStripeEvent.event_id.like("evt_p9stripe_%")
            ))
            await s.commit()


async def _seed(*, plan: str = "free", status: str = "active") -> dict:
    await _cleanup()
    async with SessionLocal() as s:
        async with bypass_tenant_scope():
            t = Tenant(handle=HANDLE, name="P9 Shop", owner_email="owner@p9.test",
                       plan=plan, status=status)
            s.add(t); await s.flush()
            owner = User(tenant_id=t.id, username=HANDLE, email="owner@p9.test",
                         role="owner", is_active=True, google_sub="sub-p9")
            s.add(owner); await s.flush()
            sub = Subscription(tenant_id=t.id, plan=plan, status=status,
                               stripe_customer_id="cus_p9_seed")
            s.add(sub)
            await s.commit()
            return {"tenant_id": t.id, "owner_id": owner.id}


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _owner_tok(ids: dict) -> str:
    return issue_access_token(tenant_id=ids["tenant_id"], user_id=ids["owner_id"], role="owner")


def _admin_tok() -> str:
    return issue_admin_token(email=ADMIN_EMAIL)


# ----- @audited decorator ----------------------------------------------------


@pytest.mark.asyncio
async def test_audited_writes_row_on_success():
    """The decorator should fire on success and capture actor/action/after_data."""
    ids = await _seed()
    try:
        @audited("test.success_action")
        async def _do(request: Request, session, admin: dict, tenant_id: int):
            return {"ok": True, "tenant_id": tenant_id}

        async with SessionLocal() as s:
            scope = {"type": "http", "client": ("203.0.113.7", 9999), "headers": [(b"x-request-id", b"rid-success")]}
            req = Request(scope=scope)
            result = await _do(
                request=req, session=s,
                admin={"email": ADMIN_EMAIL, "role": "admin"},
                tenant_id=ids["tenant_id"],
            )
            assert result == {"ok": True, "tenant_id": ids["tenant_id"]}

        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                row = (await s.execute(
                    select(AdminAuditLog).where(AdminAuditLog.action == "test.success_action")
                )).scalars().first()
        assert row is not None
        assert row.actor_email == ADMIN_EMAIL
        assert row.actor_ip == "203.0.113.7"
        assert row.request_id == "rid-success"
        assert row.tenant_id == ids["tenant_id"]
        assert row.success is True
        assert row.after_data == {"ok": True, "tenant_id": ids["tenant_id"]}
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_audited_writes_failure_row_on_exception():
    """Audit-on-failure: even when the function raises, the row must land."""
    ids = await _seed()
    try:
        @audited("test.failure_action")
        async def _explode(request: Request, session, admin: dict, tenant_id: int):
            raise ValueError("boom")

        scope = {"type": "http", "client": ("203.0.113.8", 1), "headers": [(b"x-request-id", b"rid-fail")]}
        req = Request(scope=scope)
        async with SessionLocal() as s:
            with pytest.raises(ValueError):
                await _explode(
                    request=req, session=s,
                    admin={"email": ADMIN_EMAIL, "role": "admin"},
                    tenant_id=ids["tenant_id"],
                )

        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                row = (await s.execute(
                    select(AdminAuditLog).where(AdminAuditLog.action == "test.failure_action")
                )).scalars().first()
        assert row is not None
        assert row.success is False
        assert row.after_data is None
    finally:
        await _cleanup()


# ----- admin audit router ----------------------------------------------------


@pytest.mark.asyncio
async def test_admin_audit_router_requires_admin():
    ids = await _seed()
    try:
        async with _client() as c:
            # Owner token (not admin) → 403
            r = await c.get("/admin/audit-log",
                            headers={"Authorization": f"Bearer {_owner_tok(ids)}"})
            assert r.status_code == 403, r.text

            # Admin token → 200
            r = await c.get("/admin/audit-log",
                            headers={"Authorization": f"Bearer {_admin_tok()}"})
            assert r.status_code == 200, r.text
            assert isinstance(r.json(), list)
    finally:
        await _cleanup()


# ----- plan enforcement ------------------------------------------------------


@pytest.mark.asyncio
async def test_free_plan_cashier_quota_returns_402():
    """Free plan = 1 cashier. The owner already exists (role='owner', not cashier),
    so the first cashier create succeeds; the second should 402."""
    ids = await _seed(plan="free", status="active")
    try:
        owner_tok = _owner_tok(ids)
        async with _client() as c:
            r1 = await c.post("/users", json={"pin": "318274"},
                              headers={"Authorization": f"Bearer {owner_tok}"})
            assert r1.status_code == 200, r1.text

            r2 = await c.post("/users", json={"pin": "318275"},
                              headers={"Authorization": f"Bearer {owner_tok}"})
            assert r2.status_code == 402, r2.text
            body = r2.json()["detail"]
            assert body["error"] == "quota_exceeded"
            assert body["resource"] == "cashiers"
            assert body["limit"] == 1
            assert body["current"] == 1
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_suspended_tenant_blocks_mutation_with_423():
    ids = await _seed(plan="pro", status="suspended")
    try:
        owner_tok = _owner_tok(ids)
        async with _client() as c:
            r = await c.post("/users", json={"pin": "917283"},
                             headers={"Authorization": f"Bearer {owner_tok}"})
            assert r.status_code == 423, r.text
            assert r.json()["detail"]["error"] == "tenant_suspended"
    finally:
        await _cleanup()


# ----- Stripe webhook --------------------------------------------------------


def _fake_event(*, event_id: str, event_type: str, data: dict) -> dict:
    return {"id": event_id, "type": event_type, "data": {"object": data}}


@pytest.mark.asyncio
async def test_webhook_idempotent_on_duplicate_event_id():
    """Second delivery of the same event.id returns {duplicate: true}; the local
    subscription row is updated exactly once."""
    ids = await _seed(plan="free", status="active")
    try:
        event_id = f"evt_p9stripe_{uuid.uuid4().hex[:10]}"
        # Mutate the module-level constants in lieu of pyenv-style env loading.
        # construct_event is patched below, so STRIPE_WEBHOOK_SECRET is only a
        # placeholder; STRIPE_PRICE_PRO IS read by _plan_from_subscription_object.
        config.STRIPE_PRICE_PRO = "price_TEST_PRO"
        config.STRIPE_WEBHOOK_SECRET = "whsec_TEST"

        sub_obj = {
            "id": "sub_TEST_123",
            "status": "active",
            "customer": "cus_p9_seed",
            "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            "metadata": {"tenant_id": str(ids["tenant_id"])},
            "items": {"data": [{"price": {"id": "price_TEST_PRO"}}]},
        }
        event = _fake_event(
            event_id=event_id, event_type="customer.subscription.created", data=sub_obj,
        )

        with patch("app.services.stripe_service.construct_event", return_value=event):
            async with _client() as c:
                r1 = await c.post("/subscriptions/webhook",
                                  content=json.dumps(event).encode(),
                                  headers={"stripe-signature": "t=1,v1=ignored", "content-type": "application/json"})
                assert r1.status_code == 200, r1.text
                # First delivery: applied, no duplicate flag.
                assert r1.json().get("duplicate") is not True
                assert r1.json()["outcome"]["plan"] == "pro"

                r2 = await c.post("/subscriptions/webhook",
                                  content=json.dumps(event).encode(),
                                  headers={"stripe-signature": "t=1,v1=ignored", "content-type": "application/json"})
                assert r2.status_code == 200, r2.text
                assert r2.json()["duplicate"] is True

        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                sub = (await s.execute(
                    select(Subscription).where(Subscription.tenant_id == ids["tenant_id"])
                )).scalars().first()
                tenant = (await s.execute(
                    select(Tenant).where(Tenant.id == ids["tenant_id"])
                )).scalars().first()
        assert sub is not None
        assert sub.plan == "pro"
        assert sub.status == "active"
        assert sub.stripe_subscription_id == "sub_TEST_123"
        assert tenant.plan == "pro"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_webhook_invoice_payment_failed_sets_past_due():
    ids = await _seed(plan="pro", status="active")
    try:
        event_id = f"evt_p9stripe_{uuid.uuid4().hex[:10]}"
        config.STRIPE_WEBHOOK_SECRET = "whsec_TEST"
        invoice = {
            "id": "in_TEST_1", "customer": "cus_p9_seed",
            "subscription": "sub_TEST_123",
            "subscription_details": {"metadata": {"tenant_id": str(ids["tenant_id"])}},
        }
        event = _fake_event(event_id=event_id, event_type="invoice.payment_failed", data=invoice)
        with patch("app.services.stripe_service.construct_event", return_value=event):
            async with _client() as c:
                r = await c.post("/subscriptions/webhook",
                                 content=json.dumps(event).encode(),
                                 headers={"stripe-signature": "t=1,v1=ignored", "content-type": "application/json"})
                assert r.status_code == 200, r.text

        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                sub = (await s.execute(
                    select(Subscription).where(Subscription.tenant_id == ids["tenant_id"])
                )).scalars().first()
        assert sub.status == "past_due"
        assert sub.past_due_since is not None
    finally:
        await _cleanup()
