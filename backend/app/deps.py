import os
from dataclasses import dataclass
from typing import AsyncIterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal, current_tenant_id
from app.security import decode_token

bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    user_id: int
    tenant_id: int
    role: str
    email: str | None


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def get_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Principal:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        payload = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    return Principal(
        user_id=int(payload["sub"]),
        tenant_id=int(payload["tid"]),
        role=payload["role"],
        email=payload.get("email"),
    )


async def get_tenant(p: Principal = Depends(get_principal)) -> AsyncIterator[Principal]:
    token = current_tenant_id.set(p.tenant_id)
    try:
        yield p
    finally:
        current_tenant_id.reset(token)


def require_role(*allowed: str):
    async def checker(p: Principal = Depends(get_tenant)) -> Principal:
        if p.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "role not allowed")
        return p

    return checker


def require_admin_email(p: Principal = Depends(get_principal)) -> Principal:
    allow = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
    if not p.email or p.email.lower() not in allow:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return p
