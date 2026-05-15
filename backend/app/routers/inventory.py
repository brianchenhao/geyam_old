"""Inventory snapshot + manual stock adjustments with reason dropdown."""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, constr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_session, get_tenant, require_role
from app.models.menu_item import MenuItem
from app.models.stock_movement import StockMovement
from app.services.audit import audit

router = APIRouter(prefix="/inventory", tags=["inventory"])

ADJUST_REASONS = {
    "adjust_restock", "adjust_damage", "adjust_loss", "adjust_theft",
    "adjust_miscount", "adjust_expired", "adjust_other",
}


class InventoryRow(BaseModel):
    id: int
    name: str
    stock_qty: int
    reorder_point: int
    avg_cost: Decimal
    low_stock: bool


class AdjustIn(BaseModel):
    menu_item_id: int
    delta: int  # can be positive or negative
    reason: str = Field(pattern="^adjust_(restock|damage|loss|theft|miscount|expired|other)$")
    note: Optional[constr(max_length=500)] = None


@router.get("", dependencies=[Depends(require_role("owner"))])
async def list_inventory(tenant_id: int = Depends(get_tenant),
                          session: AsyncSession = Depends(get_session)) -> list[InventoryRow]:
    rows = (await session.execute(
        select(MenuItem).where(MenuItem.is_active.is_(True)).order_by(MenuItem.name)
    )).scalars().all()
    out: list[InventoryRow] = []
    for m in rows:
        out.append(InventoryRow(
            id=m.id, name=m.name, stock_qty=m.stock_qty or 0,
            reorder_point=m.reorder_point or 0, avg_cost=m.avg_cost or Decimal(0),
            low_stock=(m.stock_qty or 0) <= (m.reorder_point or 0),
        ))
    return out


@router.get("/low-stock", dependencies=[Depends(require_role("owner"))])
async def low_stock(tenant_id: int = Depends(get_tenant),
                     session: AsyncSession = Depends(get_session)) -> list[InventoryRow]:
    rows = (await session.execute(
        select(MenuItem)
        .where(MenuItem.is_active.is_(True))
        .where(MenuItem.stock_qty <= MenuItem.reorder_point)
        .order_by(MenuItem.stock_qty)
    )).scalars().all()
    return [InventoryRow(
        id=m.id, name=m.name, stock_qty=m.stock_qty or 0,
        reorder_point=m.reorder_point or 0, avg_cost=m.avg_cost or Decimal(0),
        low_stock=True,
    ) for m in rows]


@router.post("/adjust", dependencies=[Depends(require_role("owner"))])
async def adjust(body: AdjustIn,
                  user_claims: dict = Depends(get_current_user),
                  tenant_id: int = Depends(get_tenant),
                  session: AsyncSession = Depends(get_session)) -> InventoryRow:
    if body.reason not in ADJUST_REASONS:
        raise HTTPException(status_code=400, detail=f"reason must be one of {sorted(ADJUST_REASONS)}")
    m = (await session.execute(select(MenuItem).where(MenuItem.id == body.menu_item_id))).scalars().first()
    if not m:
        raise HTTPException(status_code=404, detail="menu_item not found")
    new_stock = (m.stock_qty or 0) + body.delta
    if new_stock < 0:
        raise HTTPException(status_code=400, detail=f"adjust would make stock negative ({new_stock})")
    m.stock_qty = new_stock
    session.add(StockMovement(
        tenant_id=tenant_id, menu_item_id=m.id, delta=body.delta, reason=body.reason,
        ref_type="adjust", note=body.note, created_by=user_claims.get("user_id"),
    ))
    await audit(session, action="inventory.adjust", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="menu_item", entity_id=m.id,
                meta={"delta": body.delta, "reason": body.reason, "new_stock": new_stock})
    await session.commit()
    return InventoryRow(id=m.id, name=m.name, stock_qty=m.stock_qty,
                         reorder_point=m.reorder_point or 0, avg_cost=m.avg_cost or Decimal(0),
                         low_stock=(m.stock_qty or 0) <= (m.reorder_point or 0))
