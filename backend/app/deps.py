"""FastAPI dependencies: auth, tenant scoping, role gates."""
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import tenant_context
from app.config import ADMIN_EMAILS
from app.database import SessionLocal
from app.security import decode_token


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = authorization.split(None, 1)[1]
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    return payload


async def get_tenant(user: dict = Depends(get_current_user)) -> int:
    """Require a tenant-scoped access token and install the tenant context
    for the duration of the request so the DB hook auto-filters."""
    if user.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a tenant token")
    tenant_id = user.get("tenant_id")
    if not isinstance(tenant_id, int):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="no tenant in token")
    tenant_context.set_current_tenant_id(tenant_id)
    return tenant_id


def require_role(*roles: str):
    async def _check(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"requires role in {roles}")
        return user
    return _check


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Admin is email-based (ADMIN_EMAILS env var). Admin tokens are NOT tenant-scoped."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin only")
    if user.get("email") not in ADMIN_EMAILS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="email not whitelisted")
    return user


@asynccontextmanager
async def bypass_tenant_scope():
    """Use only in CLI / admin paths that must see across tenants."""
    tok = tenant_context.set_scope_bypass(True)
    try:
        yield
    finally:
        tenant_context._tenant_scope_bypass.reset(tok)
