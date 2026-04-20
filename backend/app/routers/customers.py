from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import Principal, get_session, require_role
from app.models import Customer
from app.services import audit

router = APIRouter(prefix="/customers", tags=["customers"])


class CustomerIn(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    notes: str | None = None


class CustomerOut(BaseModel):
    id: int
    name: str | None
    email: str | None
    phone: str | None
    notes: str | None
    model_config = {"from_attributes": True}


@router.get("", response_model=list[CustomerOut])
async def list_customers(
    search: str | None = None,
    p: Principal = Depends(require_role("owner", "cashier")),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Customer).order_by(Customer.id.desc()).limit(100)
    if search:
        pat = f"%{search}%"
        stmt = stmt.where(or_(
            Customer.name.ilike(pat), Customer.email.ilike(pat), Customer.phone.ilike(pat)
        ))
    return list(await session.scalars(stmt))


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(
    body: CustomerIn,
    p: Principal = Depends(require_role("owner", "cashier")),
    session: AsyncSession = Depends(get_session),
):
    if not any([body.name, body.email, body.phone]):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "at least one of name/email/phone required",
        )
    c = Customer(
        tenant_id=p.tenant_id, name=body.name,
        email=str(body.email) if body.email else None,
        phone=body.phone, notes=body.notes,
    )
    session.add(c)
    await session.flush()
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="customer.create", entity="customer", entity_id=c.id,
    )
    await session.commit()
    return c
