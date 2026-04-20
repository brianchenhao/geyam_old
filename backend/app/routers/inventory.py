from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import Principal, get_session, require_role
from app.models import MenuItem, StockMovement
from app.services import audit

router = APIRouter(prefix="/inventory", tags=["inventory"])

ADJUST_REASONS = {
    "adjust_damage", "adjust_loss", "adjust_theft",
    "adjust_miscount", "adjust_expired", "adjust_other",
}


class AdjustBody(BaseModel):
    menu_item_id: int
    delta: int = Field(..., description="signed; negative to shrink, positive to grow")
    reason: str
    note: str | None = None


@router.post("/adjust")
async def adjust(
    body: AdjustBody,
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    if body.reason not in ADJUST_REASONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"reason must be one of {sorted(ADJUST_REASONS)}",
        )
    if body.delta == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "delta cannot be 0")

    m = await session.get(MenuItem, body.menu_item_id)
    if m is None or m.tenant_id != p.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item not found")
    new_qty = m.stock_qty + body.delta
    if new_qty < 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"would drop stock below 0 (have {m.stock_qty}, delta {body.delta})",
        )
    m.stock_qty = new_qty
    session.add(StockMovement(
        tenant_id=p.tenant_id, menu_item_id=m.id,
        delta=body.delta, reason=body.reason, note=body.note,
        created_by=p.user_id,
    ))
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="inventory.adjust", entity="menu_item", entity_id=m.id,
        meta={"delta": body.delta, "reason": body.reason, "new_qty": new_qty},
    )
    await session.commit()
    return {"menu_item_id": m.id, "new_stock_qty": m.stock_qty}


class LowStockRow(BaseModel):
    id: int
    name: str
    stock_qty: int
    reorder_point: int


@router.get("/low-stock", response_model=list[LowStockRow])
async def low_stock(
    p: Principal = Depends(require_role("owner", "cashier")),
    session: AsyncSession = Depends(get_session),
):
    rows = await session.scalars(
        select(MenuItem)
        .where(MenuItem.is_active == True,  # noqa: E712
               MenuItem.stock_qty <= MenuItem.reorder_point)
        .order_by(MenuItem.stock_qty.asc())
    )
    return [
        LowStockRow(id=m.id, name=m.name, stock_qty=m.stock_qty,
                    reorder_point=m.reorder_point)
        for m in rows
    ]
