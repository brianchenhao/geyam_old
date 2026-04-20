from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import Principal, get_session, require_admin_email
from app.models import Tenant, TenantSettings, User

router = APIRouter(prefix="/admin/tenants", tags=["admin"])


class CreateTenant(BaseModel):
    handle: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    owner_email: EmailStr


class TenantOut(BaseModel):
    id: int
    handle: str
    name: str
    owner_email: str
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[TenantOut])
async def list_tenants(
    _: Principal = Depends(require_admin_email),
    session: AsyncSession = Depends(get_session),
):
    rows = await session.scalars(
        select(Tenant).order_by(Tenant.id).execution_options(skip_tenant_filter=True)
    )
    return list(rows)


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: CreateTenant,
    _: Principal = Depends(require_admin_email),
    session: AsyncSession = Depends(get_session),
):
    tenant = Tenant(handle=body.handle, name=body.name, owner_email=body.owner_email.lower())
    session.add(tenant)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "handle or email already exists")
    session.add(TenantSettings(tenant_id=tenant.id))
    session.add(
        User(
            tenant_id=tenant.id,
            username=f"owner.{tenant.handle}",
            email=tenant.owner_email,
            role="owner",
        )
    )
    await session.commit()
    return tenant
