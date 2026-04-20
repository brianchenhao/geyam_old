import os

from fastapi import APIRouter, Depends, HTTPException, status
from google.auth.transport import requests as grequests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.models import Tenant, User
from app.security import create_token, verify_pin
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
DEV_LOGIN = os.getenv("ENVIRONMENT", "").lower() == "development"


class GoogleLogin(BaseModel):
    id_token: str


class StaffLogin(BaseModel):
    tenant_handle: str
    username: str
    pin: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    tenant_id: int
    user_id: int


@router.post("/google", response_model=TokenOut)
async def google_login(body: GoogleLogin, session: AsyncSession = Depends(get_session)):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "google oauth not configured")
    try:
        info = google_id_token.verify_oauth2_token(
            body.id_token, grequests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid id_token")

    email = info.get("email", "").lower()
    sub = info.get("sub")
    if not email or not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "id_token missing email/sub")

    tenant = await session.scalar(select(Tenant).where(Tenant.owner_email == email))
    if tenant is None or not tenant.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no tenant for this email")

    user = await session.scalar(
        select(User).where(User.tenant_id == tenant.id, User.role == "owner")
                    .execution_options(skip_tenant_filter=True)
    )
    if user is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "owner row missing")
    if user.google_sub is None:
        user.google_sub = sub
    elif user.google_sub != sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "google_sub mismatch")

    await audit.write(
        session, tenant_id=tenant.id, user_id=user.id,
        action="auth.login.google", entity="user", entity_id=user.id,
    )
    await session.commit()

    return TokenOut(
        access_token=create_token(
            user_id=user.id, tenant_id=tenant.id, role=user.role, email=email
        ),
        role=user.role, tenant_id=tenant.id, user_id=user.id,
    )


@router.post("/staff/login", response_model=TokenOut)
async def staff_login(body: StaffLogin, session: AsyncSession = Depends(get_session)):
    tenant = await session.scalar(select(Tenant).where(Tenant.handle == body.tenant_handle))
    if tenant is None or not tenant.is_active:
        await _log_failed_login(session, None, body.username, "unknown tenant")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    user = await session.scalar(
        select(User)
        .where(User.tenant_id == tenant.id, User.username == body.username, User.role == "cashier")
        .execution_options(skip_tenant_filter=True)
    )
    if user is None or not user.is_active or not user.pin_hash or not verify_pin(body.pin, user.pin_hash):
        await _log_failed_login(session, tenant.id, body.username, "bad pin")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    await audit.write(
        session, tenant_id=tenant.id, user_id=user.id,
        action="auth.login.staff", entity="user", entity_id=user.id,
    )
    await session.commit()
    return TokenOut(
        access_token=create_token(
            user_id=user.id, tenant_id=tenant.id, role=user.role, email=None
        ),
        role=user.role, tenant_id=tenant.id, user_id=user.id,
    )


class DevOwnerLogin(BaseModel):
    tenant_handle: str


@router.post("/dev/owner", response_model=TokenOut)
async def dev_owner_login(
    body: DevOwnerLogin, session: AsyncSession = Depends(get_session),
):
    """Passwordless owner login — only enabled when ENVIRONMENT=development.
    Lets the desktop app sign in as the tenant owner without Google OAuth
    during local demos. DO NOT enable in production."""
    if not DEV_LOGIN:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "dev login disabled (ENVIRONMENT!=development)"
        )
    tenant = await session.scalar(select(Tenant).where(Tenant.handle == body.tenant_handle))
    if tenant is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown tenant")
    user = await session.scalar(
        select(User)
        .where(User.tenant_id == tenant.id, User.role == "owner")
        .execution_options(skip_tenant_filter=True)
    )
    if user is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "owner row missing")
    await audit.write(
        session, tenant_id=tenant.id, user_id=user.id,
        action="auth.login.dev_owner", entity="user", entity_id=user.id,
    )
    await session.commit()
    return TokenOut(
        access_token=create_token(
            user_id=user.id, tenant_id=tenant.id, role="owner", email=user.email
        ),
        role="owner", tenant_id=tenant.id, user_id=user.id,
    )


async def _log_failed_login(
    session: AsyncSession, tenant_id: int | None, username: str, reason: str
) -> None:
    if tenant_id is None:
        return
    await audit.write(
        session, tenant_id=tenant_id, action="auth.login.fail",
        meta={"username": username, "reason": reason},
    )
    await session.commit()
