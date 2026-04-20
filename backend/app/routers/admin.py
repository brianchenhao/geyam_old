"""Admin endpoints — gated by ADMIN_EMAILS env var. NOT tenant-scoped."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, constr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ADMIN_EMAILS
from app.deps import bypass_tenant_scope, get_session, require_admin
from app.models.tenant import Tenant
from app.models.user import User
from app.security import issue_access_token, issue_admin_token
from app.services.audit import audit

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
async def impersonate(tenant_id: int, admin: dict = Depends(require_admin),
                       session: AsyncSession = Depends(get_session)) -> dict:
    """Mint an owner-scoped JWT for the given tenant. Admin-only; every call audited."""
    async with bypass_tenant_scope():
        t = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalars().first()
        if not t:
            raise HTTPException(status_code=404, detail="tenant not found")
        owner = (await session.execute(
            select(User).where(User.tenant_id == t.id, User.role == "owner")
        )).scalars().first()
        if not owner:
            raise HTTPException(status_code=404, detail="tenant has no owner user row")
        await audit(session, action="admin.impersonate", tenant_id=t.id, user_id=owner.id,
                    meta={"admin_email": admin.get("email")})
        await session.commit()
    return {
        "access_token": issue_access_token(tenant_id=t.id, user_id=owner.id, role="owner"),
        "tenant_id": t.id,
        "tenant_handle": t.handle,
        "role": "owner",
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
