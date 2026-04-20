"""Billplz webhook receiver. Verifies x_signature using the matching tenant's
x-sign key, decrements stock inside the same DB transaction, enqueues a
receipt email when a customer is attached."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import current_tenant_id
from app.deps import get_session
from app.models import Payment, TenantSettings, Transaction
from app.routers.transaction import _mark_paid
from app.services import billplz

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/webhook")
async def webhook(
    request: Request, session: AsyncSession = Depends(get_session),
):
    """Billplz posts application/x-www-form-urlencoded."""
    form = dict(await request.form())
    bill_id = form.get("id")
    if not bill_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing bill id")

    # Find payment (and therefore tenant) — webhook is unauthenticated so we
    # look up by bill_id; the event hook filter is opt-out here via
    # skip_tenant_filter since we have no principal yet.
    payment = await session.scalar(
        select(Payment).where(Payment.bill_id == bill_id)
        .execution_options(skip_tenant_filter=True)
    )
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown bill")

    settings = await session.get(TenantSettings, payment.tenant_id)
    if not settings or not billplz.verify_webhook(settings, form):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad signature")

    # Now scope the rest of the session to the right tenant.
    tok = current_tenant_id.set(payment.tenant_id)
    try:
        payment.state = form.get("state", payment.state)
        payment.raw_payload = form

        tx = await session.scalar(
            select(Transaction)
            .options(selectinload(Transaction.items))
            .where(Transaction.id == payment.transaction_id)
        )
        if tx is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "tx missing")

        if form.get("paid") == "true" and tx.status == "pending":
            await _mark_paid(session, tx, payment.tenant_id, form, via="webhook")
        await session.commit()
    finally:
        current_tenant_id.reset(tok)

    # Return Billplz's required 200 so it stops retrying.
    return {"ok": True}
