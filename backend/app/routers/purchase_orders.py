"""Purchase order lifecycle: draft → sent → partial → received.

Receiving (partial or full) updates:
  - menu_items.stock_qty (atomic per line)
  - menu_items.avg_cost via weighted-average formula:
        new_avg = (old_stock*old_avg + recv_qty*unit_cost) / (old_stock + recv_qty)
  - stock_movements row per line (reason='po_receive')
  - purchase_order_items.quantity_received accumulates
  - po.status transitions sent → partial → received
"""
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import Principal, get_session, require_role
from app.models import MenuItem, PurchaseOrder, PurchaseOrderItem, StockMovement
from app.services import audit

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


class POLineIn(BaseModel):
    menu_item_id: int
    quantity_ordered: int = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)


class POCreate(BaseModel):
    supplier_id: int | None = None
    expected_at: date | None = None
    items: list[POLineIn] = Field(min_length=1)


class POLineOut(BaseModel):
    id: int
    menu_item_id: int | None
    quantity_ordered: int
    quantity_received: int
    unit_cost: Decimal
    model_config = {"from_attributes": True}


class POOut(BaseModel):
    id: int
    supplier_id: int | None
    status: str
    expected_at: date | None
    received_at: datetime | None
    total_cost: Decimal
    items: list[POLineOut]
    model_config = {"from_attributes": True}


class POReceiveLine(BaseModel):
    po_item_id: int
    quantity_received: int = Field(gt=0)


class POReceive(BaseModel):
    lines: list[POReceiveLine] = Field(min_length=1)


async def _fetch(session: AsyncSession, po_id: int, tenant_id: int) -> PurchaseOrder:
    po = await session.scalar(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.items))
        .where(PurchaseOrder.id == po_id)
    )
    if po is None or po.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return po


@router.get("", response_model=list[POOut])
async def list_pos(
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    rows = await session.scalars(
        select(PurchaseOrder).options(selectinload(PurchaseOrder.items))
        .order_by(PurchaseOrder.id.desc()).limit(100)
    )
    return list(rows)


@router.post("", response_model=POOut, status_code=status.HTTP_201_CREATED)
async def create_po(
    body: POCreate,
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    total = sum(Decimal(str(l.unit_cost)) * l.quantity_ordered for l in body.items)
    po = PurchaseOrder(
        tenant_id=p.tenant_id, supplier_id=body.supplier_id,
        status="draft", expected_at=body.expected_at,
        created_by=p.user_id, total_cost=total,
    )
    session.add(po)
    await session.flush()
    for l in body.items:
        session.add(PurchaseOrderItem(
            po_id=po.id, menu_item_id=l.menu_item_id,
            quantity_ordered=l.quantity_ordered, unit_cost=l.unit_cost,
        ))
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="po.create", entity="purchase_order", entity_id=po.id,
    )
    await session.commit()
    return await _fetch(session, po.id, p.tenant_id)


@router.post("/{po_id}/send", response_model=POOut)
async def send_po(
    po_id: int,
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    po = await _fetch(session, po_id, p.tenant_id)
    if po.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, f"po not draft ({po.status})")
    po.status = "sent"
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="po.send", entity="purchase_order", entity_id=po.id,
    )
    await session.commit()
    return await _fetch(session, po.id, p.tenant_id)


@router.post("/{po_id}/cancel", response_model=POOut)
async def cancel_po(
    po_id: int,
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    po = await _fetch(session, po_id, p.tenant_id)
    if po.status in ("received", "cancelled"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"po is {po.status}")
    po.status = "cancelled"
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="po.cancel", entity="purchase_order", entity_id=po.id,
    )
    await session.commit()
    return await _fetch(session, po.id, p.tenant_id)


@router.post("/{po_id}/receive", response_model=POOut)
async def receive_po(
    po_id: int,
    body: POReceive,
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    po = await _fetch(session, po_id, p.tenant_id)
    if po.status not in ("sent", "partial"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"po not receivable ({po.status})"
        )
    items_by_id = {i.id: i for i in po.items}

    for line in body.lines:
        poi = items_by_id.get(line.po_item_id)
        if poi is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"po_item {line.po_item_id} not in PO"
            )
        remaining = poi.quantity_ordered - poi.quantity_received
        if line.quantity_received > remaining:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"can't receive {line.quantity_received} (only {remaining} outstanding)",
            )
        if poi.menu_item_id is None:
            continue

        m = await session.get(MenuItem, poi.menu_item_id)
        if m is None:
            continue

        # Weighted-average cost update
        recv = Decimal(line.quantity_received)
        old_stock = Decimal(m.stock_qty)
        old_avg = Decimal(str(m.avg_cost or 0))
        new_stock = old_stock + recv
        new_avg = (
            (old_stock * old_avg + recv * Decimal(str(poi.unit_cost))) / new_stock
            if new_stock > 0 else Decimal("0")
        )
        m.stock_qty = int(new_stock)
        m.avg_cost = new_avg.quantize(Decimal("0.01"))

        poi.quantity_received += line.quantity_received

        session.add(StockMovement(
            tenant_id=p.tenant_id, menu_item_id=m.id,
            delta=line.quantity_received, reason="po_receive",
            ref_type="purchase_order", ref_id=po.id,
            created_by=p.user_id,
        ))

    fully_received = all(i.quantity_received >= i.quantity_ordered for i in po.items)
    any_received = any(i.quantity_received > 0 for i in po.items)
    if fully_received:
        po.status = "received"
        po.received_at = datetime.utcnow()
    elif any_received:
        po.status = "partial"

    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="po.receive", entity="purchase_order", entity_id=po.id,
        meta={"lines": [l.model_dump() for l in body.lines]},
    )
    await session.commit()
    return await _fetch(session, po.id, p.tenant_id)
