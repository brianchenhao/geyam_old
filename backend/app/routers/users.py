from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import Principal, get_session, require_role
from app.models import Tenant, User
from app.security import hash_pin
from app.services import audit

router = APIRouter(prefix="/users", tags=["users"])


class CreateCashier(BaseModel):
    pin: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class ResetPin(BaseModel):
    pin: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_cashier(
    body: CreateCashier,
    owner: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    tenant = await session.get(Tenant, owner.tenant_id)
    count = await session.scalar(
        select(func.count()).select_from(User).where(User.role == "cashier")
    )
    username = f"staff{(count or 0) + 1}.{tenant.handle}"
    user = User(
        tenant_id=owner.tenant_id,
        username=username,
        pin_hash=hash_pin(body.pin),
        role="cashier",
    )
    session.add(user)
    await session.flush()
    await audit.write(
        session, tenant_id=owner.tenant_id, user_id=owner.user_id,
        action="user.create", entity="user", entity_id=user.id,
        meta={"username": username},
    )
    await session.commit()
    return user


@router.patch("/{user_id}/reset_pin", response_model=UserOut)
async def reset_pin(
    user_id: int,
    body: ResetPin,
    owner: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, user_id)
    if user is None or user.tenant_id != owner.tenant_id or user.role != "cashier":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cashier not found")
    user.pin_hash = hash_pin(body.pin)
    await audit.write(
        session, tenant_id=owner.tenant_id, user_id=owner.user_id,
        action="user.reset_pin", entity="user", entity_id=user.id,
    )
    await session.commit()
    return user


@router.get("", response_model=list[UserOut])
async def list_users(
    owner: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    rows = await session.scalars(select(User).order_by(User.id))
    return list(rows)
