"""Plan-quota enforcement.

Source of truth: ``tenants.plan`` + ``tenants.status`` (mirrored from
``subscriptions`` by the Stripe webhook). Calling routers ask, before each
mutation:

  - ``ensure_active(tenant)`` — 423 Locked if tenant is suspended (used for
    mutations the cashier shouldn't be doing while past-due grace expired)
  - ``ensure_cashier_quota(session, tenant)`` — 402 if creating one more
    cashier would breach the per-plan limit
  - ``ensure_item_quota(session, tenant)`` — 402 likewise for menu items
  - ``ensure_openai_quota(session, tenant)`` — 402 likewise for the monthly
    vision-call budget
  - ``ensure_training_quota(session, tenant)`` — 402 likewise for weekly
    training submissions

Limit numbers come from PLAN-stage3-Geyam.md §"Free/Pro/Business tier limits":
  Free      1 cashier   50 items    100 openai/mo    1 training/wk
  Pro       5 cashiers  500 items   500 openai/mo    5 training/wk
  Business  unlimited   unlimited   2000 openai/mo  20 training/wk
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.menu_item import MenuItem
from app.models.openai_usage import OpenAIUsage
from app.models.tenant import Tenant
from app.models.training_job import TrainingJob
from app.models.user import User

UNLIMITED = -1  # sentinel — no cap


@dataclass(frozen=True)
class PlanLimits:
    cashiers: int          # max simultaneously active cashier users
    items: int             # max non-archived menu items
    openai_monthly: int    # OpenAI vision calls per calendar month
    training_weekly: int   # training jobs queued per rolling 7 days


PLAN_LIMITS: dict[str, PlanLimits] = {
    "free":     PlanLimits(cashiers=1,          items=50,        openai_monthly=100,  training_weekly=1),
    "pro":      PlanLimits(cashiers=5,          items=500,       openai_monthly=500,  training_weekly=5),
    "business": PlanLimits(cashiers=UNLIMITED,  items=UNLIMITED, openai_monthly=2000, training_weekly=20),
}


def get_limits(plan: str) -> PlanLimits:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


# ----- status check ----------------------------------------------------------


def ensure_active(tenant: Tenant) -> None:
    """Block mutations from a suspended tenant. 423 Locked is the canonical
    'service exists but is locked for billing reasons' status."""
    if tenant.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={
                "error": "tenant_suspended",
                "message": "Subscription past-due grace period expired. "
                           "Update payment in the billing portal to restore service.",
            },
        )


# ----- quota checks ----------------------------------------------------------


async def ensure_cashier_quota(session: AsyncSession, tenant: Tenant) -> None:
    """Raise 402 if creating one more cashier would exceed the plan cap.
    Counts only active cashiers — soft-deleted (is_active=False) don't count."""
    limit = get_limits(tenant.plan).cashiers
    if limit == UNLIMITED:
        return
    current = (await session.execute(
        select(func.count()).select_from(User).where(
            User.tenant_id == tenant.id, User.role == "cashier", User.is_active.is_(True),
        )
    )).scalar() or 0
    if current >= limit:
        _raise_402("cashiers", current, limit, tenant.plan)


async def ensure_item_quota(session: AsyncSession, tenant: Tenant) -> None:
    limit = get_limits(tenant.plan).items
    if limit == UNLIMITED:
        return
    current = (await session.execute(
        select(func.count()).select_from(MenuItem).where(
            MenuItem.tenant_id == tenant.id, MenuItem.is_active.is_(True),
        )
    )).scalar() or 0
    if current >= limit:
        _raise_402("menu_items", current, limit, tenant.plan)


async def ensure_openai_quota(session: AsyncSession, tenant: Tenant) -> None:
    """OpenAI is monthly-budgeted. Sum the per-day counters for the current
    calendar month and compare against the plan cap."""
    limit = get_limits(tenant.plan).openai_monthly
    if limit == UNLIMITED:
        return
    today = date.today()
    month_start = today.replace(day=1)
    current = (await session.execute(
        select(func.coalesce(func.sum(OpenAIUsage.calls), 0)).where(
            OpenAIUsage.tenant_id == tenant.id, OpenAIUsage.day >= month_start,
        )
    )).scalar() or 0
    if int(current) >= limit:
        _raise_402("openai_calls_this_month", int(current), limit, tenant.plan)


async def ensure_training_quota(session: AsyncSession, tenant: Tenant) -> None:
    """Rolling 7-day cap on queued/training jobs."""
    limit = get_limits(tenant.plan).training_weekly
    if limit == UNLIMITED:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    current = (await session.execute(
        select(func.count()).select_from(TrainingJob).where(
            TrainingJob.tenant_id == tenant.id, TrainingJob.queued_at >= cutoff,
        )
    )).scalar() or 0
    if current >= limit:
        _raise_402("training_jobs_last_7d", current, limit, tenant.plan)


# ----- helpers ---------------------------------------------------------------


async def load_tenant(session: AsyncSession, tenant_id: int) -> Tenant:
    """Helper for endpoints that don't already hold a Tenant ref. Uses the
    bypass context so the tenant root row is reachable even from within the
    tenant-scoped query layer."""
    from app.deps import bypass_tenant_scope
    async with bypass_tenant_scope():
        t = (await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalars().first()
    if t is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    return t


def _raise_402(resource: str, current: int, limit: int, plan: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "error": "quota_exceeded",
            "resource": resource,
            "current": current,
            "limit": limit,
            "plan": plan,
            "message": (f"Plan '{plan}' allows {limit} {resource}; you are at {current}. "
                        f"Upgrade via /subscriptions/checkout."),
        },
    )
