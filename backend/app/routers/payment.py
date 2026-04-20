"""Phase 8 — /payments/webhook: Billplz v3 state change callback."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import bypass_tenant_scope, get_session
from app.models.menu_item import MenuItem
from app.models.payment import Payment
from app.models.stock_movement import StockMovement
from app.models.tenant_settings import TenantSettings
from app.models.transaction import Transaction, TransactionItem
from app.services.audit import audit
from app.services.billplz import verify_webhook_signature
from app.services.crypto import decrypt_secret

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/webhook")
async def webhook(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    form = await request.form()
    fields = {k: str(v) for k, v in form.items()}
    x_signature = fields.pop("x_signature", "")

    tenant_id_str = fields.get("reference_1") or ""
    tx_id_str = fields.get("reference_2") or ""
    try:
        tenant_id = int(tenant_id_str)
        tx_id = int(tx_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad references in webhook")

    async with bypass_tenant_scope():
        ts = (await session.execute(
            select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
        )).scalars().first()
        if ts is None or not ts.billplz_xsign_key:
            raise HTTPException(status_code=400, detail="tenant missing xsign key")
        xsign = decrypt_secret(ts.billplz_xsign_key) or ""

        # The original posted payload includes x_signature — pass it back in for canonical signing
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
            # receipt email enqueue placeholder — Phase 9 will wire it here

        await session.commit()

    return {"status": "ok"}
