from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import Principal, get_session, require_role
from app.models import Supplier
from app.services import audit

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    contact: str | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    notes: str | None = None


class SupplierOut(BaseModel):
    id: int
    name: str
    contact: str | None
    email: str | None
    phone: str | None
    notes: str | None
    model_config = {"from_attributes": True}


@router.get("", response_model=list[SupplierOut])
async def list_suppliers(
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    rows = await session.scalars(select(Supplier).order_by(Supplier.name))
    return list(rows)


@router.post("", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    body: SupplierIn,
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    s = Supplier(
        tenant_id=p.tenant_id, name=body.name, contact=body.contact,
        email=str(body.email) if body.email else None, phone=body.phone, notes=body.notes,
    )
    session.add(s)
    await session.flush()
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="supplier.create", entity="supplier", entity_id=s.id,
    )
    await session.commit()
    return s


@router.patch("/{sid}", response_model=SupplierOut)
async def update_supplier(
    sid: int,
    body: SupplierIn,
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    s = await session.get(Supplier, sid)
    if s is None or s.tenant_id != p.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    s.name = body.name
    s.contact = body.contact
    s.email = str(body.email) if body.email else None
    s.phone = body.phone
    s.notes = body.notes
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="supplier.update", entity="supplier", entity_id=s.id,
    )
    await session.commit()
    return s


@router.delete("/{sid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(
    sid: int,
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    s = await session.get(Supplier, sid)
    if s is None or s.tenant_id != p.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    await session.delete(s)
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="supplier.delete", entity="supplier", entity_id=sid,
    )
    await session.commit()
    return None
