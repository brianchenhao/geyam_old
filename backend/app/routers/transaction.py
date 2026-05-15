"""Phase 8 — transactions + Billplz QR + manual/owner void + list/detail."""
import base64
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from typing import Optional

import qrcode

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from redis import Redis
from rq import Queue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import REDIS_URL
from app.deps import get_current_user, get_session, get_tenant, require_role
from app.models.menu_item import MenuItem
from app.models.payment import Payment
from app.models.stock_movement import StockMovement
from app.models.tenant import Tenant
from app.models.tenant_settings import TenantSettings
from app.models.transaction import Transaction, TransactionItem
from app.services.audit import audit
from app.services.billplz import create_bill, fetch_bill
from app.services.crypto import decrypt_secret
from app.services.tx_numbering import next_tx_number
from app.websocket import hub

router = APIRouter(tags=["transactions"])


class LineItemIn(BaseModel):
    menu_item_id: int
    quantity: int = Field(ge=1, default=1)
    confidence: Optional[float] = None
    source: Optional[str] = Field(default="manual", pattern="^(yolo|mediapipe|openai|manual)$")


class TransactionCreateIn(BaseModel):
    items: list[LineItemIn] = Field(min_length=1)
    receipt_email: Optional[str] = None


class LineItemOut(BaseModel):
    menu_item_id: Optional[int]
    quantity: int
    unit_price: Decimal
    confidence: Optional[float] = None
    source: Optional[str] = None

    model_config = {"from_attributes": True}


class TransactionOut(BaseModel):
    id: int
    tenant_id: int
    tx_number: str
    total: Decimal
    payment_method: str
    payment_ref: Optional[str] = None
    status: str
    staff_id: Optional[int] = None
    receipt_email: Optional[str] = None
    created_at: datetime
    paid_at: Optional[datetime] = None
    voided_at: Optional[datetime] = None
    items: list[LineItemOut] = []

    model_config = {"from_attributes": True}


async def _tx_to_out(session: AsyncSession, tx: Transaction) -> TransactionOut:
    items = (await session.execute(
        select(TransactionItem).where(TransactionItem.transaction_id == tx.id)
    )).scalars().all()
    return TransactionOut(
        id=tx.id, tenant_id=tx.tenant_id, tx_number=tx.tx_number, total=tx.total,
        payment_method=tx.payment_method, payment_ref=tx.payment_ref, status=tx.status,
        staff_id=tx.staff_id, receipt_email=tx.receipt_email, created_at=tx.created_at,
        paid_at=tx.paid_at, voided_at=tx.voided_at,
        items=[LineItemOut.model_validate(i) for i in items],
    )


@router.post("/transaction")
async def create_transaction(
    body: TransactionCreateIn,
    user_claims: dict = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> TransactionOut:
    item_ids = [li.menu_item_id for li in body.items]
    menu_rows = (await session.execute(
        select(MenuItem).where(MenuItem.id.in_(item_ids))
    )).scalars().all()
    m_by_id = {m.id: m for m in menu_rows}
    if len(m_by_id) != len(set(item_ids)):
        raise HTTPException(status_code=400, detail="unknown menu_item_id in items")

    merged: dict[int, tuple[int, Decimal, Optional[float], Optional[str]]] = {}
    for li in body.items:
        m = m_by_id[li.menu_item_id]
        if m.id in merged:
            q, p, c, s = merged[m.id]
            merged[m.id] = (q + li.quantity, p, c, s)
        else:
            merged[m.id] = (li.quantity, m.price, li.confidence, li.source)

    for mid, (qty, _p, _c, _s) in merged.items():
        if m_by_id[mid].stock_qty < qty:
            raise HTTPException(status_code=400,
                                detail=f"insufficient stock for {m_by_id[mid].name}: have {m_by_id[mid].stock_qty}, need {qty}")

    total = Decimal("0")
    for _mid, (qty, price, _c, _s) in merged.items():
        total += price * qty

    tx_number = await next_tx_number(session, tenant_id)
    tx = Transaction(
        tenant_id=tenant_id, tx_number=tx_number, staff_id=user_claims.get("user_id"),
        receipt_email=body.receipt_email, total=total, payment_method="qr", status="pending",
    )
    session.add(tx)
    await session.flush()

    for mid, (qty, price, conf, src) in merged.items():
        session.add(TransactionItem(
            transaction_id=tx.id, menu_item_id=mid, quantity=qty,
            unit_price=price, confidence=conf, source=src or "manual",
        ))

    await audit(session, action="tx.create", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="transaction", entity_id=tx.id,
                meta={"tx_number": tx_number, "total": str(total), "items": len(merged)})
    await session.commit()
    await session.refresh(tx)
    return await _tx_to_out(session, tx)


@router.post("/transaction/{tx_id}/qr")
async def request_qr(
    tx_id: int,
    user_claims: dict = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tx = (await session.execute(select(Transaction).where(Transaction.id == tx_id))).scalars().first()
    if not tx:
        raise HTTPException(status_code=404, detail="transaction not found")
    if tx.status != "pending":
        raise HTTPException(status_code=400, detail=f"tx not pending (status={tx.status})")

    ts = (await session.execute(select(TenantSettings).where(TenantSettings.tenant_id == tenant_id))).scalars().first()
    if ts is None or not (ts.billplz_api_key and ts.billplz_collection_id and ts.billplz_xsign_key):
        raise HTTPException(status_code=400, detail="Configure Billplz in Settings")

    api_key = decrypt_secret(ts.billplz_api_key)
    tenant = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalars().first()
    shop_email = ts.shop_contact_email or (tenant.owner_email if tenant else "noreply@geyam.com")

    try:
        bill = create_bill(
            mode=ts.billplz_mode or "sandbox",
            api_key=api_key,
            collection_id=ts.billplz_collection_id,
            name=tx.tx_number,
            email=shop_email,
            amount_cents=int(tx.total * 100),
            description=tx.tx_number,
            callback_url="https://api.geyam.com/payments/webhook",
            redirect_url="https://geyam.com/payment-complete",
            reference_1=str(tenant_id),
            reference_2=str(tx.id),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"billplz failure: {type(e).__name__}")

    session.add(Payment(
        tenant_id=tenant_id, transaction_id=tx.id, provider="billplz",
        bill_id=bill.get("id"), bill_url=bill.get("url"), amount=tx.total, state="due",
        raw_payload=bill,
    ))
    await session.commit()

    bill_url = bill.get("url") or ""
    img = qrcode.make(bill_url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    bill_qr_png = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    return {
        "bill_id": bill.get("id"),
        "bill_url": bill_url,
        "bill_qr_png": bill_qr_png,
        "amount": str(tx.total),
        "tx_number": tx.tx_number,
    }


_receipt_queue: Queue | None = None


def _get_receipt_queue() -> Queue:
    global _receipt_queue
    if _receipt_queue is None:
        _receipt_queue = Queue("geyam", connection=Redis.from_url(REDIS_URL))
    return _receipt_queue


@router.post("/transaction/{tx_id}/recheck-billplz", dependencies=[Depends(require_role("owner"))])
async def recheck_billplz(
    tx_id: int,
    user_claims: dict = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> TransactionOut:
    """Plan step 50 — poll Billplz for a bill we may have missed the webhook for.

    If the bill comes back as paid while the tx is still pending, apply the same
    state transition the webhook would (decrement stock, enqueue receipt, ws notify).
    """
    tx = (await session.execute(select(Transaction).where(Transaction.id == tx_id))).scalars().first()
    if not tx:
        raise HTTPException(status_code=404, detail="transaction not found")

    payment = (await session.execute(
        select(Payment).where(Payment.transaction_id == tx.id)
    )).scalars().first()
    if not payment or not payment.bill_id:
        raise HTTPException(status_code=400, detail="no bill attached to this transaction")

    ts = (await session.execute(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )).scalars().first()
    if ts is None or not ts.billplz_api_key:
        raise HTTPException(status_code=400, detail="Billplz not configured")
    api_key = decrypt_secret(ts.billplz_api_key)

    try:
        bill = fetch_bill(mode=ts.billplz_mode or "sandbox", api_key=api_key, bill_id=payment.bill_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"billplz fetch failed: {type(e).__name__}")

    paid_bool = bool(bill.get("paid")) or (str(bill.get("state") or "").lower() == "paid")
    payment.raw_payload = bill
    payment.state = "paid" if paid_bool else (bill.get("state") or payment.state)

    just_paid = paid_bool and tx.status == "pending"
    if just_paid:
        tx.status = "paid"
        tx.paid_at = datetime.utcnow()
        tx.payment_method = "qr"
        tx.payment_ref = payment.bill_id
        payment.paid_at = datetime.utcnow()

        items = (await session.execute(
            select(TransactionItem).where(TransactionItem.transaction_id == tx.id)
        )).scalars().all()
        for ti in items:
            if ti.menu_item_id is None or not ti.quantity:
                continue
            m = (await session.execute(select(MenuItem).where(MenuItem.id == ti.menu_item_id))).scalars().first()
            if m:
                m.stock_qty = max((m.stock_qty or 0) - ti.quantity, 0)
                session.add(StockMovement(
                    tenant_id=tenant_id, menu_item_id=m.id, delta=-ti.quantity,
                    reason="sale", ref_type="transaction", ref_id=tx.id,
                ))
        try:
            _get_receipt_queue().enqueue(
                "app.services.receipt_jobs.send_receipt_for_tx",
                tenant_id, tx.id, job_timeout="5m",
            )
        except Exception:
            pass

    await audit(session, action="tx.recheck", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="transaction", entity_id=tx.id,
                meta={"bill_id": payment.bill_id, "paid": paid_bool, "state_transitioned": just_paid})
    await session.commit()
    await session.refresh(tx)

    if just_paid:
        await hub.publish(tenant_id, {
            "type": "tx_paid",
            "tx_id": tx.id,
            "tx_number": tx.tx_number,
            "total": str(tx.total),
            "bill_id": payment.bill_id,
            "via": "recheck",
        })

    return await _tx_to_out(session, tx)


@router.post("/transaction/{tx_id}/void")
async def void_transaction(
    tx_id: int,
    user_claims: dict = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> TransactionOut:
    tx = (await session.execute(select(Transaction).where(Transaction.id == tx_id))).scalars().first()
    if not tx:
        raise HTTPException(status_code=404, detail="transaction not found")
    if tx.status != "pending":
        raise HTTPException(status_code=400, detail="only pending transactions can be voided via this endpoint")
    tx.status = "voided"
    tx.voided_at = datetime.utcnow()
    tx.voided_by = user_claims.get("user_id")
    await audit(session, action="tx.void", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="transaction", entity_id=tx.id)
    await session.commit()
    await session.refresh(tx)
    return await _tx_to_out(session, tx)


class OverrideVoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/transaction/{tx_id}/override-void", dependencies=[Depends(require_role("owner"))])
async def override_void(
    tx_id: int,
    body: OverrideVoidIn,
    user_claims: dict = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> TransactionOut:
    tx = (await session.execute(select(Transaction).where(Transaction.id == tx_id))).scalars().first()
    if not tx:
        raise HTTPException(status_code=404, detail="transaction not found")
    if tx.status != "paid":
        raise HTTPException(status_code=400, detail="override-void requires status=paid")

    items = (await session.execute(select(TransactionItem).where(TransactionItem.transaction_id == tx.id))).scalars().all()
    for ti in items:
        if ti.menu_item_id:
            m = (await session.execute(select(MenuItem).where(MenuItem.id == ti.menu_item_id))).scalars().first()
            if m:
                m.stock_qty = (m.stock_qty or 0) + (ti.quantity or 0)
                session.add(StockMovement(
                    tenant_id=tenant_id, menu_item_id=m.id, delta=ti.quantity,
                    reason="void_restore", ref_type="transaction", ref_id=tx.id,
                    created_by=user_claims.get("user_id"),
                    note=f"override_void: {body.reason[:200]}",
                ))
    tx.status = "voided"
    tx.voided_at = datetime.utcnow()
    tx.voided_by = user_claims.get("user_id")
    await audit(session, action="tx.override_void", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="transaction", entity_id=tx.id,
                meta={"reason": body.reason})
    await session.commit()
    await session.refresh(tx)
    return await _tx_to_out(session, tx)


@router.get("/transactions")
async def list_transactions(
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> list[TransactionOut]:
    stmt = select(Transaction).order_by(Transaction.id.desc()).offset((page - 1) * page_size).limit(page_size)
    if status:
        stmt = stmt.where(Transaction.status == status)
    rows = (await session.execute(stmt)).scalars().all()
    return [await _tx_to_out(session, tx) for tx in rows]


@router.get("/transactions/{tx_id}")
async def get_transaction(
    tx_id: int,
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> TransactionOut:
    tx = (await session.execute(select(Transaction).where(Transaction.id == tx_id))).scalars().first()
    if not tx:
        raise HTTPException(status_code=404, detail="transaction not found")
    return await _tx_to_out(session, tx)
