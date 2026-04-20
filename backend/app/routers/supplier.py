"""Suppliers CRUD (owner-only)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, constr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_session, get_tenant, require_role
from app.models.supplier import Supplier
from app.services.audit import audit

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


class SupplierIn(BaseModel):
    name: constr(strip_whitespace=True, min_length=1, max_length=100)
    contact: Optional[constr(max_length=100)] = None
    email: Optional[EmailStr] = None
    phone: Optional[constr(max_length=30)] = None
    notes: Optional[str] = None


class SupplierOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    contact: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("")
async def list_suppliers(include_archived: bool = False,
                          tenant_id: int = Depends(get_tenant),
                          session: AsyncSession = Depends(get_session)) -> list[SupplierOut]:
    stmt = select(Supplier).order_by(Supplier.name)
    if not include_archived:
        stmt = stmt.where(Supplier.is_active.is_(True))
    rows = (await session.execute(stmt)).scalars().all()
    return [SupplierOut.model_validate(r) for r in rows]


@router.post("", dependencies=[Depends(require_role("owner"))])
async def create_supplier(body: SupplierIn,
                           user_claims: dict = Depends(get_current_user),
                           tenant_id: int = Depends(get_tenant),
                           session: AsyncSession = Depends(get_session)) -> SupplierOut:
    sup = Supplier(tenant_id=tenant_id, **body.model_dump(exclude_none=True))
    session.add(sup); await session.flush()
    await audit(session, action="supplier.create", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="supplier", entity_id=sup.id,
                meta={"name": body.name})
    await session.commit(); await session.refresh(sup)
    return SupplierOut.model_validate(sup)


@router.patch("/{sid}", dependencies=[Depends(require_role("owner"))])
async def patch_supplier(sid: int, body: SupplierIn,
                          user_claims: dict = Depends(get_current_user),
                          tenant_id: int = Depends(get_tenant),
                          session: AsyncSession = Depends(get_session)) -> SupplierOut:
    sup = (await session.execute(select(Supplier).where(Supplier.id == sid))).scalars().first()
    if not sup:
        raise HTTPException(status_code=404, detail="supplier not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(sup, k, v)
    await audit(session, action="supplier.update", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="supplier", entity_id=sup.id)
    await session.commit(); await session.refresh(sup)
    return SupplierOut.model_validate(sup)


@router.delete("/{sid}", dependencies=[Depends(require_role("owner"))])
async def delete_supplier(sid: int, user_claims: dict = Depends(get_current_user),
                           tenant_id: int = Depends(get_tenant),
                           session: AsyncSession = Depends(get_session)) -> SupplierOut:
    sup = (await session.execute(select(Supplier).where(Supplier.id == sid))).scalars().first()
    if not sup:
        raise HTTPException(status_code=404, detail="supplier not found")
    sup.is_active = False
    await audit(session, action="supplier.delete", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="supplier", entity_id=sup.id)
    await session.commit(); await session.refresh(sup)
    return SupplierOut.model_validate(sup)


@router.post("/{sid}/restore", dependencies=[Depends(require_role("owner"))])
async def restore_supplier(sid: int, user_claims: dict = Depends(get_current_user),
                            tenant_id: int = Depends(get_tenant),
                            session: AsyncSession = Depends(get_session)) -> SupplierOut:
    sup = (await session.execute(select(Supplier).where(Supplier.id == sid))).scalars().first()
    if not sup:
        raise HTTPException(status_code=404, detail="supplier not found")
    sup.is_active = True
    await audit(session, action="supplier.restore", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="supplier", entity_id=sup.id)
    await session.commit(); await session.refresh(sup)
    return SupplierOut.model_validate(sup)
