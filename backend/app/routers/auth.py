"""Phase 3 — auth for owners (Google OAuth) and cashiers (username + PIN)."""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, constr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ADMIN_EMAILS, JWT_ALGORITHM, JWT_SECRET
from app.deps import bypass_tenant_scope, get_current_user, get_session
from app.models.onboarding_state import OnboardingState
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.models.user import User
from app.security import (
    REFRESH_TOKEN_DAYS,
    decode_token,
    issue_access_token,
    issue_admin_token,
    issue_signup_token,
    verify_pin,
)
import re
from app.services.audit import audit
from app.services.google_oauth import verify_google_access_token, verify_google_id_token

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleLoginIn(BaseModel):
    id_token: str | None = None
    access_token: str | None = None


class GoogleSignupIn(BaseModel):
    signup_token: str
    shop_name: constr(strip_whitespace=True, min_length=2, max_length=100)
    handle: constr(strip_whitespace=True, min_length=2, max_length=50)


HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")


class StaffLoginIn(BaseModel):
    tenant_handle: constr(strip_whitespace=True, min_length=2, max_length=50)
    username: constr(strip_whitespace=True, min_length=2, max_length=80)
    pin: constr(strip_whitespace=True, min_length=6, max_length=6)


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str | None = None
    role: str
    tenant_id: int | None = None
    user_id: int | None = None


def _issue_refresh_token(*, tenant_id: int, user_id: int, role: str) -> str:
    payload = {
        "tenant_id": tenant_id, "user_id": user_id, "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
        "iat": datetime.now(timezone.utc), "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@router.post("/google")
async def google_login(body: GoogleLoginIn, session: AsyncSession = Depends(get_session)):
    try:
        if body.id_token:
            claims = verify_google_id_token(body.id_token)
        elif body.access_token:
            claims = verify_google_access_token(body.access_token)
        else:
            raise ValueError("id_token or access_token required")
    except Exception as e:
        async with bypass_tenant_scope():
            await audit(session, action="auth.login_fail", meta={"method": "google", "reason": str(e)[:200]})
            await session.commit()
        raise HTTPException(status_code=401, detail="google token invalid")

    email = claims["email"].lower()
    sub = claims["sub"]

    if email in ADMIN_EMAILS:
        async with bypass_tenant_scope():
            await audit(session, action="auth.login_success",
                        meta={"method": "google", "admin": True, "email": email})
            await session.commit()
        return TokenOut(access_token=issue_admin_token(email=email), role="admin")

    async with bypass_tenant_scope():
        tenant = (await session.execute(
            select(Tenant).where(Tenant.owner_email == email)
        )).scalars().first()
        if not tenant:
            await audit(session, action="auth.signup_start",
                        meta={"method": "google", "email": email})
            await session.commit()
            return {
                "needs_onboarding": True,
                "signup_token": issue_signup_token(email=email, sub=sub),
                "email": email,
            }

        user = (await session.execute(
            select(User).where(User.tenant_id == tenant.id, User.role == "owner")
        )).scalars().first()
        if not user:
            await audit(session, action="auth.login_fail", tenant_id=tenant.id,
                        meta={"method": "google", "reason": "owner_row_missing"})
            await session.commit()
            raise HTTPException(status_code=500, detail="tenant has no owner user row")

        if not user.google_sub:
            user.google_sub = sub
        await audit(session, action="auth.login_success", tenant_id=tenant.id, user_id=user.id,
                    meta={"method": "google"})
        await session.commit()

    return TokenOut(
        access_token=issue_access_token(tenant_id=tenant.id, user_id=user.id, role="owner"),
        refresh_token=_issue_refresh_token(tenant_id=tenant.id, user_id=user.id, role="owner"),
        role="owner", tenant_id=tenant.id, user_id=user.id,
    )


@router.post("/google/signup", response_model=TokenOut)
async def google_signup(body: GoogleSignupIn, session: AsyncSession = Depends(get_session)):
    try:
        claims = decode_token(body.signup_token)
    except Exception:
        raise HTTPException(status_code=401, detail="signup token invalid or expired")
    if claims.get("type") != "signup":
        raise HTTPException(status_code=401, detail="not a signup token")

    email = claims["email"].lower()
    sub = claims["sub"]
    handle = body.handle.lower()
    if not HANDLE_RE.match(handle):
        raise HTTPException(status_code=400, detail="handle must be lowercase letters, digits, hyphen; 2-50 chars")

    async with bypass_tenant_scope():
        existing = (await session.execute(
            select(Tenant).where((Tenant.handle == handle) | (Tenant.owner_email == email))
        )).scalars().first()
        if existing:
            if existing.owner_email == email:
                raise HTTPException(status_code=409, detail="you already have a shop — sign in instead")
            raise HTTPException(status_code=409, detail="handle already taken — pick another")

        tenant = Tenant(handle=handle, name=body.shop_name, owner_email=email)
        session.add(tenant)
        await session.flush()
        user = User(
            tenant_id=tenant.id, username=handle, email=email,
            google_sub=sub, role="owner", is_active=True,
        )
        session.add(user)
        # Phase 10: every new tenant lands on the Free plan, with the onboarding
        # wizard at step 1. Subscription rows are mandatory now that Phase 9
        # plan-enforcement code reads `subscriptions.plan` on every quota check.
        session.add(Subscription(tenant_id=tenant.id, plan="free", status="active"))
        session.add(OnboardingState(tenant_id=tenant.id, step=1))
        await session.flush()
        await audit(session, action="tenant.create", tenant_id=tenant.id, user_id=user.id,
                    meta={"via": "self_signup", "email": email, "handle": handle})
        await audit(session, action="auth.login_success", tenant_id=tenant.id, user_id=user.id,
                    meta={"method": "google", "first_login": True})
        await session.commit()

    return TokenOut(
        access_token=issue_access_token(tenant_id=tenant.id, user_id=user.id, role="owner"),
        refresh_token=_issue_refresh_token(tenant_id=tenant.id, user_id=user.id, role="owner"),
        role="owner", tenant_id=tenant.id, user_id=user.id,
    )


@router.post("/staff/login", response_model=TokenOut)
async def staff_login(body: StaffLoginIn, session: AsyncSession = Depends(get_session)):
    async with bypass_tenant_scope():
        tenant = (await session.execute(
            select(Tenant).where(Tenant.handle == body.tenant_handle)
        )).scalars().first()
        if not tenant:
            await audit(session, action="auth.login_fail",
                        meta={"method": "pin", "reason": "bad_tenant", "handle": body.tenant_handle})
            await session.commit()
            raise HTTPException(status_code=401, detail="invalid credentials")

        user = (await session.execute(
            select(User).where(
                User.tenant_id == tenant.id,
                User.username == body.username,
                User.role == "cashier",
                User.is_active.is_(True),
            )
        )).scalars().first()
        if not user or not user.pin_hash or not verify_pin(body.pin, user.pin_hash):
            await audit(session, action="auth.login_fail", tenant_id=tenant.id,
                        meta={"method": "pin", "reason": "bad_pin", "username": body.username})
            await session.commit()
            raise HTTPException(status_code=401, detail="invalid credentials")

        await audit(session, action="auth.login_success", tenant_id=tenant.id, user_id=user.id,
                    meta={"method": "pin"})
        await session.commit()

    return TokenOut(
        access_token=issue_access_token(tenant_id=tenant.id, user_id=user.id, role="cashier"),
        refresh_token=_issue_refresh_token(tenant_id=tenant.id, user_id=user.id, role="cashier"),
        role="cashier", tenant_id=tenant.id, user_id=user.id,
    )


@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn):
    try:
        claims = decode_token(body.refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid refresh token")
    if claims.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="not a refresh token")
    tenant_id, user_id, role = claims["tenant_id"], claims["user_id"], claims["role"]
    return TokenOut(
        access_token=issue_access_token(tenant_id=tenant_id, user_id=user_id, role=role),
        role=role, tenant_id=tenant_id, user_id=user_id,
    )


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    async with bypass_tenant_scope():
        await audit(session, action="auth.logout",
                    tenant_id=user.get("tenant_id"), user_id=user.get("user_id"),
                    meta={"role": user.get("role")})
        await session.commit()
    return {"status": "ok"}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user
