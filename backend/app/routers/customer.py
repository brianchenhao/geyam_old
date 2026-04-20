"""Customers CRUD — owner lists/edits, cashier can create from checkout dialog."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, constr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_session, get_tenant
from app.models.customer import Customer
from app.services.audit import audit

router = APIRouter(prefix="/customers", tags=["customers"])


class CustomerIn(BaseModel):
    name: Optional[constr(strip_whitespace=True, max_length=100)] = None
    email: Optional[EmailStr] = None
    phone: Optional[constr(max_length=30)] = None
    notes: Optional[str] = None


class CustomerOut(BaseModel):
    id: int
    tenant_id: int
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


@router.get("")
async def list_customers(tenant_id: int = Depends(get_tenant),
                          session: AsyncSession = Depends(get_session)) -> list[CustomerOut]:
    rows = (await session.execute(select(Customer).order_by(Customer.id.desc()))).scalars().all()
    return [CustomerOut.model_validate(r) for r in rows]


@router.post("")
async def create_customer(body: CustomerIn,
                            user_claims: dict = Depends(get_current_user),
                            tenant_id: int = Depends(get_tenant),
                            session: AsyncSession = Depends(get_session)) -> CustomerOut:
    if not any([body.name, body.email, body.phone]):
        raise HTTPException(status_code=400, detail="at least one of name/email/phone required")

    # Dedup by (tenant_id, email) if email provided
    if body.email:
        existing = (await session.execute(
            select(Customer).where(Customer.email == body.email)
        )).scalars().first()
        if existing:
            return CustomerOut.model_validate(existing)

    c = Customer(tenant_id=tenant_id, **body.model_dump(exclude_none=True))
    session.add(c); await session.flush()
    await audit(session, action="customer.create", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="customer", entity_id=c.id)
    await session.commit(); await session.refresh(c)
    return CustomerOut.model_validate(c)
