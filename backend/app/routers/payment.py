"""Phase 8 — /payments/webhook: Billplz v3 state change callback."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from redis import Redis
from rq import Queue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import REDIS_URL
from app.deps import bypass_tenant_scope, get_session
from app.models.menu_item import MenuItem
from app.models.payment import Payment
from app.models.stock_movement import StockMovement
from app.models.tenant_settings import TenantSettings
from app.models.transaction import Transaction, TransactionItem
from app.services.audit import audit
from app.services.billplz import verify_webhook_signature
from app.services.crypto import decrypt_secret
from app.websocket import hub

router = APIRouter(prefix="/payments", tags=["payments"])

_receipt_queue: Queue | None = None


def _get_receipt_queue() -> Queue:
    global _receipt_queue
    if _receipt_queue is None:
        _receipt_queue = Queue("geyam", connection=Redis.from_url(REDIS_URL))
    return _receipt_queue


@router.post("/webhook")
async def webhook(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    form = await request.form()
    fields = {k: str(v) for k, v in form.items()}
    x_signature = fields.pop("x_signature", "")

    bill_id_in = fields.get("id") or ""
    async with bypass_tenant_scope():
        existing_payment = (await session.execute(
            select(Payment).where(Payment.bill_id == bill_id_in)
        )).scalars().first()
        if existing_payment is None:
            raise HTTPException(status_code=400, detail="unknown bill_id")
        tenant_id = existing_payment.tenant_id
        tx_id = existing_payment.transaction_id

        ts = (await session.execute(
            select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
        )).scalars().first()
        if ts is None or not ts.billplz_xsign_key:
            raise HTTPException(status_code=400, detail="tenant missing xsign key")
        xsign = decrypt_secret(ts.billplz_xsign_key) or ""

        signing_fields = dict(fields)
        if not verify_webhook_signature(xsign_key=xsign, form_fields=signing_fields, x_signature=x_signature):
            await audit(session, action="tx.pay_webhook_badsig", tenant_id=tenant_id,
                        entity="transaction", entity_id=tx_id, meta={"fields": list(fields.keys())})
            await session.commit()
            raise HTTPException(status_code=400, detail="bad signature")

        tx = (await session.execute(select(Transaction).where(Transaction.id == tx_id))).scalars().first()
        if not tx or tx.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="transaction not found")

        bill_id = fields.get("id") or fields.get("billplz[id]") or ""
        paid_raw = (fields.get("paid") or fields.get("billplz[paid]") or "false").lower()
        state_raw = (fields.get("state") or fields.get("billplz[state]") or "").lower()
        paid_bool = paid_raw in ("true", "1") or state_raw == "paid"

        payment = (await session.execute(
            select(Payment).where(Payment.transaction_id == tx.id)
        )).scalars().first()
        if payment is None:
            payment = Payment(tenant_id=tenant_id, transaction_id=tx.id, provider="billplz",
                              bill_id=bill_id, state="due")
            session.add(payment)
        payment.raw_payload = fields
        payment.state = "paid" if paid_bool else state_raw or payment.state

        if paid_bool and tx.status == "pending":
            tx.status = "paid"
            tx.paid_at = datetime.utcnow()
            tx.payment_method = "qr"
            tx.payment_ref = bill_id
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
            await audit(session, action="tx.pay", tenant_id=tenant_id,
                        entity="transaction", entity_id=tx.id,
                        meta={"bill_id": bill_id})
            try:
                _get_receipt_queue().enqueue(
                    "app.services.receipt_jobs.send_receipt_for_tx",
                    tenant_id, tx.id, job_timeout="5m",
                )
            except Exception:
                pass

        await session.commit()

    if paid_bool:
        await hub.publish(tenant_id, {
            "type": "tx_paid",
            "tx_id": tx.id,
            "tx_number": tx.tx_number,
            "total": str(tx.total),
            "bill_id": bill_id,
        })

    return {"status": "ok"}
