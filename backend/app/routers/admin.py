"""Admin endpoints — gated by ADMIN_EMAILS env var. NOT tenant-scoped."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, constr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ADMIN_EMAILS, DEMO_TENANT_HANDLE
from app.deps import bypass_tenant_scope, get_session, require_admin
from app.models.admin_audit_log import AdminAuditLog
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.models.user import User
from app.security import issue_access_token, issue_admin_token
from app.services.audit import audit, audited

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminLoginIn(BaseModel):
    email: EmailStr


@router.post("/dev-login")
async def admin_dev_login(body: AdminLoginIn):
    """Phase 2 placeholder for admin login. Real Google-OAuth-backed admin sign-in
    is wired in Phase 3 at /auth/google (same email whitelist). Returns an admin JWT
    if the email is in ADMIN_EMAILS — useful for creating the first tenant before
    the Google flow is done."""
    if body.email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="email not whitelisted")
    return {"token": issue_admin_token(email=body.email)}


class TenantCreateIn(BaseModel):
    handle: constr(strip_whitespace=True, min_length=2, max_length=50)
    name: constr(strip_whitespace=True, min_length=2, max_length=100)
    owner_email: EmailStr


class TenantOut(BaseModel):
    id: int
    handle: str
    name: str
    owner_email: str

    model_config = {"from_attributes": True}


@router.get("/tenants", dependencies=[Depends(require_admin)])
async def list_tenants(session: AsyncSession = Depends(get_session)) -> list[TenantOut]:
    async with bypass_tenant_scope():
        res = await session.execute(select(Tenant).order_by(Tenant.id))
    return [TenantOut.model_validate(t) for t in res.scalars().all()]


@router.post("/tenants/{tenant_id}/impersonate", dependencies=[Depends(require_admin)])
@audited("admin.impersonate.start")
async def impersonate(
    tenant_id: int,
    request: Request,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Mint an owner-scoped JWT for the demo tenant. Admin-only.

    Phase 10: only `DEMO_TENANT_HANDLE` is impersonatable. Real paying tenants
    are intentionally off-limits — "support session" must go through a separate
    consented flow, not the admin back door.

    Every call is recorded in admin_audit_log via @audited (paired with
    /impersonate/stop) so the trail of admin-into-tenant sessions is auditable.
    """
    async with bypass_tenant_scope():
        t = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalars().first()
        if not t:
            raise HTTPException(status_code=404, detail="tenant not found")
        if t.handle != DEMO_TENANT_HANDLE:
            raise HTTPException(
                status_code=403,
                detail=f"impersonation is restricted to the demo tenant ({DEMO_TENANT_HANDLE})",
            )
        owner = (await session.execute(
            select(User).where(User.tenant_id == t.id, User.role == "owner")
        )).scalars().first()
        if not owner:
            raise HTTPException(status_code=404, detail="tenant has no owner user row")
    return {
        "access_token": issue_access_token(tenant_id=t.id, user_id=owner.id, role="owner"),
        "tenant_id": t.id,
        "tenant_handle": t.handle,
        "role": "owner",
    }


@router.post("/tenants/{tenant_id}/impersonate/stop", dependencies=[Depends(require_admin)])
@audited("admin.impersonate.stop")
async def impersonate_stop(
    tenant_id: int,
    request: Request,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Counterpart to impersonate(): client signals it has discarded the
    impersonation JWT. Stateless — the actual access cutoff is the client
    forgetting the token (JWT can't be server-revoked without a denylist) —
    but the audit row gives a clean session boundary for the trail."""
    return {"tenant_id": tenant_id, "stopped": True}


@router.get("/funnel", dependencies=[Depends(require_admin)])
async def funnel(session: AsyncSession = Depends(get_session)) -> dict:
    """Self-serve signup funnel snapshot for the admin dashboard tile.

    Returns:
      signups: {today, week, month, all_time}     — new tenants by window
      subscriptions: {free, pro, business}        — active counts per plan
      conversion_rate: float                       — paid / total tenants
      recent_admin_actions: [{ts, actor, action, success, tenant_id}, ...]
    """
    # tenants.created_at is TIMESTAMP WITHOUT TIME ZONE (Stage 2 legacy), so
    # comparisons must be naive UTC. AdminAuditLog.ts uses timezone-aware,
    # but the comparison there happens server-side via .desc().limit() — no
    # bound datetime needed.
    now = datetime.utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    async with bypass_tenant_scope():
        async def _count_since(since: datetime) -> int:
            r = await session.execute(
                select(func.count()).select_from(Tenant).where(Tenant.created_at >= since)
            )
            return int(r.scalar_one())

        total = (await session.execute(
            select(func.count()).select_from(Tenant)
        )).scalar_one()

        sub_rows = (await session.execute(
            select(Subscription.plan, func.count())
            .where(Subscription.status == "active")
            .group_by(Subscription.plan)
        )).all()
        plans = {p: int(c) for p, c in sub_rows}
        paid = plans.get("pro", 0) + plans.get("business", 0)

        recent = (await session.execute(
            select(AdminAuditLog).order_by(AdminAuditLog.id.desc()).limit(20)
        )).scalars().all()

        return {
            "signups": {
                "today": await _count_since(day_start),
                "week": await _count_since(week_start),
                "month": await _count_since(month_start),
                "all_time": int(total),
            },
            "subscriptions": {
                "free": plans.get("free", 0),
                "pro": plans.get("pro", 0),
                "business": plans.get("business", 0),
            },
            "conversion_rate": round(paid / total, 4) if total else 0.0,
            "recent_admin_actions": [
                {
                    "ts": r.ts.isoformat(),
                    "actor": r.actor_email,
                    "action": r.action,
                    "success": r.success,
                    "tenant_id": r.tenant_id,
                }
                for r in recent
            ],
        }


@router.post("/tenants", dependencies=[Depends(require_admin)])
async def create_tenant(body: TenantCreateIn, session: AsyncSession = Depends(get_session)) -> TenantOut:
    async with bypass_tenant_scope():
        existing = (await session.execute(
            select(Tenant).where(
                (Tenant.handle == body.handle) | (Tenant.owner_email == body.owner_email)
            )
        )).scalars().first()
        if existing:
            raise HTTPException(status_code=409, detail="handle or owner_email already exists")
        tenant = Tenant(handle=body.handle, name=body.name, owner_email=body.owner_email)
        session.add(tenant)
        await session.flush()
        # Pre-create the owner user row; google_sub will be filled on first Google login.
        owner = User(
            tenant_id=tenant.id,
            username=body.handle,
            email=body.owner_email,
            role="owner",
        )
        session.add(owner)
        await session.commit()
        await session.refresh(tenant)
    return TenantOut.model_validate(tenant)
