"""Purchase orders — draft → sent → partial/received → cancelled.

Receiving updates stock_movements, menu_items.stock_qty, and recomputes
weighted-average cost: avg_cost = (old_stock*old_avg + recv*unit_cost) / new_stock.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_session, get_tenant, require_role
from app.models.menu_item import MenuItem
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.stock_movement import StockMovement
from app.services.audit import audit

router = APIRouter(prefix="/purchase-orders", tags=["purchase_orders"])


class POItemIn(BaseModel):
    menu_item_id: int
    quantity_ordered: int = Field(ge=1)
    unit_cost: Decimal = Field(ge=0)


class POCreateIn(BaseModel):
    supplier_id: Optional[int] = None
    expected_at: Optional[date] = None
    items: list[POItemIn] = Field(min_length=1)


class POItemOut(BaseModel):
    id: int
    menu_item_id: Optional[int]
    quantity_ordered: int
    quantity_received: int
    unit_cost: Decimal

    model_config = {"from_attributes": True}


class POOut(BaseModel):
    id: int
    tenant_id: int
    supplier_id: Optional[int]
    status: str
    expected_at: Optional[date]
    received_at: Optional[datetime]
    total_cost: Decimal
    created_at: datetime
    items: list[POItemOut] = []

    model_config = {"from_attributes": True}


async def _po_to_out(session: AsyncSession, po: PurchaseOrder) -> POOut:
    items = (await session.execute(select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po.id))).scalars().all()
    return POOut(id=po.id, tenant_id=po.tenant_id, supplier_id=po.supplier_id, status=po.status,
                  expected_at=po.expected_at, received_at=po.received_at, total_cost=po.total_cost,
                  created_at=po.created_at, items=[POItemOut.model_validate(i) for i in items])


@router.get("", dependencies=[Depends(require_role("owner"))])
async def list_pos(status: Optional[str] = None,
                    tenant_id: int = Depends(get_tenant),
                    session: AsyncSession = Depends(get_session)) -> list[POOut]:
    stmt = select(PurchaseOrder).order_by(PurchaseOrder.id.desc())
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    rows = (await session.execute(stmt)).scalars().all()
    return [await _po_to_out(session, r) for r in rows]


@router.post("", dependencies=[Depends(require_role("owner"))])
async def create_po(body: POCreateIn,
                     user_claims: dict = Depends(get_current_user),
                     tenant_id: int = Depends(get_tenant),
                     session: AsyncSession = Depends(get_session)) -> POOut:
    total = sum((li.unit_cost * li.quantity_ordered for li in body.items), Decimal("0"))
    po = PurchaseOrder(tenant_id=tenant_id, supplier_id=body.supplier_id, status="draft",
                       expected_at=body.expected_at, created_by=user_claims.get("user_id"),
                       total_cost=total)
    session.add(po); await session.flush()
    for li in body.items:
        session.add(PurchaseOrderItem(po_id=po.id, menu_item_id=li.menu_item_id,
                                       quantity_ordered=li.quantity_ordered,
                                       unit_cost=li.unit_cost))
    await audit(session, action="po.create", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="po", entity_id=po.id,
                meta={"items": len(body.items), "total": str(total)})
    await session.commit(); await session.refresh(po)
    return await _po_to_out(session, po)


@router.post("/{po_id}/send", dependencies=[Depends(require_role("owner"))])
async def send_po(po_id: int, user_claims: dict = Depends(get_current_user),
                   tenant_id: int = Depends(get_tenant),
                   session: AsyncSession = Depends(get_session)) -> POOut:
    po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))).scalars().first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status != "draft":
        raise HTTPException(status_code=400, detail="only draft POs can be sent")
    po.status = "sent"
    await audit(session, action="po.send", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="po", entity_id=po.id)
    await session.commit(); await session.refresh(po)
    return await _po_to_out(session, po)


class ReceiveLineIn(BaseModel):
    po_item_id: int
    quantity_received: int = Field(ge=1)


class ReceiveIn(BaseModel):
    lines: list[ReceiveLineIn] = Field(min_length=1)


@router.post("/{po_id}/receive", dependencies=[Depends(require_role("owner"))])
async def receive_po(po_id: int, body: ReceiveIn,
                      user_claims: dict = Depends(get_current_user),
                      tenant_id: int = Depends(get_tenant),
                      session: AsyncSession = Depends(get_session)) -> POOut:
    po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))).scalars().first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status not in ("sent", "partial"):
        raise HTTPException(status_code=400, detail=f"cannot receive on status={po.status}")

    recv_by_id = {r.po_item_id: r.quantity_received for r in body.lines}
    items = (await session.execute(select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po.id))).scalars().all()

    for ti in items:
        add_qty = recv_by_id.get(ti.id, 0)
        if add_qty <= 0:
            continue
        remaining = ti.quantity_ordered - ti.quantity_received
        if add_qty > remaining:
            raise HTTPException(status_code=400, detail=f"line {ti.id}: receive {add_qty} > remaining {remaining}")

        if ti.menu_item_id is not None:
            m = (await session.execute(select(MenuItem).where(MenuItem.id == ti.menu_item_id))).scalars().first()
            if m:
                old_stock = m.stock_qty or 0
                old_avg = Decimal(m.avg_cost or 0)
                new_stock = old_stock + add_qty
                if new_stock > 0:
                    m.avg_cost = ((Decimal(old_stock) * old_avg) + (ti.unit_cost * add_qty)) / Decimal(new_stock)
                m.stock_qty = new_stock
                session.add(StockMovement(
                    tenant_id=tenant_id, menu_item_id=m.id, delta=add_qty,
                    reason="po_receive", ref_type="purchase_order", ref_id=po.id,
                    created_by=user_claims.get("user_id"),
                ))
        ti.quantity_received = ti.quantity_received + add_qty

    fully = all((ti.quantity_received >= ti.quantity_ordered) for ti in items)
    po.status = "received" if fully else "partial"
    if fully:
        po.received_at = datetime.utcnow()

    await audit(session, action="po.receive", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="po", entity_id=po.id,
                meta={"fully_received": fully})
    await session.commit(); await session.refresh(po)
    return await _po_to_out(session, po)


@router.post("/{po_id}/cancel", dependencies=[Depends(require_role("owner"))])
async def cancel_po(po_id: int, user_claims: dict = Depends(get_current_user),
                     tenant_id: int = Depends(get_tenant),
                     session: AsyncSession = Depends(get_session)) -> POOut:
    po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))).scalars().first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status in ("received", "cancelled"):
        raise HTTPException(status_code=400, detail=f"cannot cancel status={po.status}")
    po.status = "cancelled"
    await audit(session, action="po.cancel", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="po", entity_id=po.id)
    await session.commit(); await session.refresh(po)
    return await _po_to_out(session, po)
