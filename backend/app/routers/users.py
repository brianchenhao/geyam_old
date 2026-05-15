"""Owner-only cashier management.

- POST /users      → create cashier (custom username, or auto = staffN.<handle> if blank; bcrypt PIN)
- PATCH /users/{id} → reset PIN or toggle is_active
- DELETE /users/{id} → soft-delete
- GET /users       → list cashiers for this tenant
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, constr
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import bypass_tenant_scope, get_current_user, get_session, get_tenant, require_role
from app.models.tenant import Tenant
from app.models.user import User
from app.security import hash_pin
from app.services.audit import audit

router = APIRouter(prefix="/users", tags=["users"])

# PINs too guessable; match the plan's blocklist.
TRIVIAL_PINS = {
    "000000","111111","222222","333333","444444","555555","666666","777777","888888","999999",
    "123456","654321","012345",
}

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")


class CashierCreateIn(BaseModel):
    pin: constr(strip_whitespace=True, min_length=6, max_length=6)
    username: constr(strip_whitespace=True, min_length=0, max_length=32) | None = None


class CashierPatchIn(BaseModel):
    pin: constr(strip_whitespace=True, min_length=6, max_length=6) | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    id: int
    tenant_id: int
    username: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


def _validate_pin(pin: str) -> None:
    if not pin.isdigit():
        raise HTTPException(status_code=400, detail="PIN must be 6 digits")
    if pin in TRIVIAL_PINS:
        raise HTTPException(status_code=400, detail="PIN is on the blocklist; choose a less guessable one")


@router.get("", dependencies=[Depends(require_role("owner"))])
async def list_cashiers(tenant_id: int = Depends(get_tenant),
                        session: AsyncSession = Depends(get_session)) -> list[UserOut]:
    res = await session.execute(select(User).where(User.role == "cashier").order_by(User.id))
    return [UserOut.model_validate(u) for u in res.scalars().all()]


@router.post("", dependencies=[Depends(require_role("owner"))])
async def create_cashier(body: CashierCreateIn,
                          user_claims: dict = Depends(get_current_user),
                          tenant_id: int = Depends(get_tenant),
                          session: AsyncSession = Depends(get_session)) -> UserOut:
    _validate_pin(body.pin)

    # Owner's handle (used as the staff suffix) comes from the tenant row.
    async with bypass_tenant_scope():
        tenant = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant missing")

    submitted = (body.username or "").strip().lower()
    if submitted:
        if not USERNAME_RE.match(submitted):
            raise HTTPException(
                status_code=400,
                detail="Username must be 2–32 chars, lowercase letters/digits/._-, starting with a letter or digit",
            )
        username = submitted
    else:
        n_existing = (await session.execute(
            select(func.count()).select_from(User).where(User.role == "cashier")
        )).scalar() or 0
        username = f"staff{n_existing + 1}.{tenant.handle}"

    cashier = User(
        tenant_id=tenant_id, username=username, role="cashier",
        pin_hash=hash_pin(body.pin), is_active=True,
    )
    session.add(cashier)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail=f"Username '{username}' is already taken")
    await audit(session, action="user.create", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="user", entity_id=cashier.id,
                meta={"username": username})
    await session.commit()
    await session.refresh(cashier)
    return UserOut.model_validate(cashier)


@router.patch("/{user_id}", dependencies=[Depends(require_role("owner"))])
async def patch_cashier(user_id: int, body: CashierPatchIn,
                         user_claims: dict = Depends(get_current_user),
                         tenant_id: int = Depends(get_tenant),
                         session: AsyncSession = Depends(get_session)) -> UserOut:
    cashier = (await session.execute(
        select(User).where(User.id == user_id, User.role == "cashier")
    )).scalars().first()
    if not cashier:
        raise HTTPException(status_code=404, detail="cashier not found")

    changes: dict = {}
    if body.pin is not None:
        _validate_pin(body.pin)
        cashier.pin_hash = hash_pin(body.pin)
        changes["pin_reset"] = True
        await audit(session, action="user.reset_pin", tenant_id=tenant_id,
                    user_id=user_claims.get("user_id"), entity="user", entity_id=cashier.id)
    if body.is_active is not None:
        cashier.is_active = body.is_active
        changes["is_active"] = body.is_active
        await audit(session, action="user.update", tenant_id=tenant_id,
                    user_id=user_claims.get("user_id"), entity="user", entity_id=cashier.id,
                    meta=changes)
    await session.commit()
    await session.refresh(cashier)
    return UserOut.model_validate(cashier)


@router.delete("/{user_id}", dependencies=[Depends(require_role("owner"))])
async def deactivate_cashier(user_id: int,
                              user_claims: dict = Depends(get_current_user),
                              tenant_id: int = Depends(get_tenant),
                              session: AsyncSession = Depends(get_session)) -> UserOut:
    cashier = (await session.execute(
        select(User).where(User.id == user_id, User.role == "cashier")
    )).scalars().first()
    if not cashier:
        raise HTTPException(status_code=404, detail="cashier not found")
    cashier.is_active = False
    await audit(session, action="user.deactivate", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="user", entity_id=cashier.id)
    await session.commit()
    await session.refresh(cashier)
    return UserOut.model_validate(cashier)
