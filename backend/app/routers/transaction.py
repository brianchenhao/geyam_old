"""Phase 8 — transactions + QR creation + void + re-check."""
import os
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import Principal, get_session, require_role
from app.models import (
    Customer,
    MenuItem,
    Payment,
    TenantSettings,
    Transaction,
    TransactionItem,
)
from app.services import audit, billplz, ws_hub
from app.services.billplz import BillplzConfigError
from app.services.tx_numbering import next_number

router = APIRouter(prefix="/transaction", tags=["transaction"])


class TxLine(BaseModel):
    menu_item_id: int
    quantity: int = Field(gt=0)
    confidence: float | None = None
    source: str | None = None


class TxCreate(BaseModel):
    items: list[TxLine] = Field(min_length=1)
    customer_id: int | None = None
    payment_method: str = Field(default="qr", pattern=r"^(cash|qr)$")


class TxItemOut(BaseModel):
    menu_item_id: int | None
    quantity: int
    unit_price: Decimal
    confidence: float | None
    source: str | None
    model_config = {"from_attributes": True}


class TxOut(BaseModel):
    id: int
    tx_number: str
    total: Decimal
    status: str
    payment_method: str
    payment_ref: str | None
    customer_id: int | None
    items: list[TxItemOut]
    created_at: datetime
    paid_at: datetime | None
    voided_at: datetime | None
    model_config = {"from_attributes": True}


class QrOut(BaseModel):
    bill_id: str
    bill_url: str


@router.post("", response_model=TxOut, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    body: TxCreate,
    p: Principal = Depends(require_role("owner", "cashier")),
    session: AsyncSession = Depends(get_session),
):
    # Load menu items + lock rows so two cashiers can't sell the last unit.
    ids = [l.menu_item_id for l in body.items]
    rows = (await session.scalars(
        select(MenuItem).where(MenuItem.id.in_(ids)).with_for_update()
    )).all()
    by_id = {m.id: m for m in rows}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"menu items not found: {missing}"
        )

    total = Decimal("0")
    for line in body.items:
        m = by_id[line.menu_item_id]
        if not m.is_active:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"item '{m.name}' not active"
            )
        if m.stock_qty < line.quantity:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"insufficient stock for '{m.name}' "
                f"(have {m.stock_qty}, need {line.quantity})",
            )
        total += Decimal(str(m.price)) * line.quantity

    if body.customer_id is not None:
        cust = await session.get(Customer, body.customer_id)
        if cust is None or cust.tenant_id != p.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found")

    tx_number = await next_number(session, tenant_id=p.tenant_id)
    tx = Transaction(
        tenant_id=p.tenant_id,
        tx_number=tx_number,
        staff_id=p.user_id,
        customer_id=body.customer_id,
        total=total,
        payment_method=body.payment_method,
        status="pending",
    )
    session.add(tx)
    await session.flush()

    for line in body.items:
        m = by_id[line.menu_item_id]
        session.add(TransactionItem(
            transaction_id=tx.id,
            menu_item_id=m.id,
            quantity=line.quantity,
            unit_price=m.price,
            confidence=line.confidence,
            source=line.source,
        ))

    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="tx.create", entity="transaction", entity_id=tx.id,
        meta={"tx_number": tx.tx_number, "total": str(total)},
    )
    await session.commit()
    return await _fetch_with_items(session, tx.id)


async def _fetch_with_items(session: AsyncSession, tx_id: int) -> Transaction:
    tx = await session.scalar(
        select(Transaction)
        .options(selectinload(Transaction.items))
        .where(Transaction.id == tx_id)
    )
    return tx


@router.get("/{tx_id}", response_model=TxOut)
async def get_tx(
    tx_id: int,
    p: Principal = Depends(require_role("owner", "cashier")),
    session: AsyncSession = Depends(get_session),
):
    tx = await _fetch_with_items(session, tx_id)
    if tx is None or tx.tenant_id != p.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return tx


@router.get("", response_model=list[TxOut])
async def list_tx(
    limit: int = 50,
    p: Principal = Depends(require_role("owner", "cashier")),
    session: AsyncSession = Depends(get_session),
):
    rows = await session.scalars(
        select(Transaction)
        .options(selectinload(Transaction.items))
        .order_by(Transaction.id.desc())
        .limit(limit)
    )
    return list(rows)


@router.post("/{tx_id}/qr", response_model=QrOut)
async def create_qr(
    tx_id: int,
    p: Principal = Depends(require_role("owner", "cashier")),
    session: AsyncSession = Depends(get_session),
):
    tx = await session.get(Transaction, tx_id)
    if tx is None or tx.tenant_id != p.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    if tx.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"tx not pending ({tx.status})")

    settings = await session.get(TenantSettings, p.tenant_id)
    try:
        cb_base = os.getenv("BILLPLZ_CALLBACK_BASE", "https://api.geyam.com")
        bill = await billplz.create_bill(
            settings,
            name=f"Sale {tx.tx_number}",
            email=None, mobile=None,
            amount_sen=int(Decimal(str(tx.total)) * 100),
            description=f"Sale {tx.tx_number}",
            callback_url=f"{cb_base}/payments/webhook",
            reference_1_label="tx_id", reference_1=str(tx.id),
        )
    except BillplzConfigError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Billplz credentials not configured — set them in Settings",
        )
    except Exception as e:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Billplz error: {e}"
        )

    session.add(Payment(
        tenant_id=p.tenant_id, transaction_id=tx.id,
        provider="billplz", bill_id=bill.get("id"),
        bill_url=bill.get("url"), amount=tx.total, state="due",
        raw_payload=bill,
    ))
    tx.payment_ref = bill.get("id")
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="tx.qr_created", entity="transaction", entity_id=tx.id,
        meta={"bill_id": bill.get("id")},
    )
    await session.commit()
    return QrOut(bill_id=bill["id"], bill_url=bill["url"])


class VoidBody(BaseModel):
    reason: str | None = None


@router.post("/{tx_id}/void", response_model=TxOut)
async def void_tx(
    tx_id: int,
    body: VoidBody,
    p: Principal = Depends(require_role("owner", "cashier")),
    session: AsyncSession = Depends(get_session),
):
    tx = await _fetch_with_items(session, tx_id)
    if tx is None or tx.tenant_id != p.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    if tx.status == "voided":
        return tx
    if tx.status == "paid" and p.role != "owner":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "only owner can override-void a paid tx"
        )

    previous = tx.status
    tx.status = "voided"
    tx.voided_at = datetime.utcnow()
    tx.voided_by = p.user_id

    action = "tx.void" if previous == "pending" else "tx.override_void"
    meta = {"previous": previous}
    if body.reason:
        meta["reason"] = body.reason

    # Owner override-void of a paid tx must restore stock.
    if previous == "paid":
        from app.models import MenuItem, StockMovement
        for it in tx.items:
            if it.menu_item_id is None:
                continue
            m = await session.get(MenuItem, it.menu_item_id)
            if m:
                m.stock_qty += it.quantity
            session.add(StockMovement(
                tenant_id=p.tenant_id, menu_item_id=it.menu_item_id,
                delta=it.quantity, reason="adjust_other",
                ref_type="transaction", ref_id=tx.id,
                note="override-void stock restore",
                created_by=p.user_id,
            ))

    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action=action, entity="transaction", entity_id=tx.id, meta=meta,
    )
    await session.commit()
    return await _fetch_with_items(session, tx.id)


@router.post("/{tx_id}/recheck", response_model=TxOut)
async def recheck_billplz(
    tx_id: int,
    p: Principal = Depends(require_role("owner", "cashier")),
    session: AsyncSession = Depends(get_session),
):
    """Poll Billplz directly for the bill's current state and apply it if paid.
    Safety net for missed webhooks."""
    tx = await _fetch_with_items(session, tx_id)
    if tx is None or tx.tenant_id != p.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    if not tx.payment_ref:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no bill_id on tx")
    settings = await session.get(TenantSettings, p.tenant_id)
    try:
        bill = await billplz.get_bill(settings, tx.payment_ref)
    except BillplzConfigError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billplz creds missing")
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Billplz error: {e}")

    if bill.get("paid") and tx.status == "pending":
        await _mark_paid(session, tx, p.tenant_id, bill, via="recheck")
        await session.commit()
    return await _fetch_with_items(session, tx.id)


async def _mark_paid(
    session: AsyncSession,
    tx: Transaction,
    tenant_id: int,
    raw: dict,
    *,
    via: str,
) -> None:
    """Shared 'mark as paid' path — webhook AND recheck call this."""
    from app.models import MenuItem, StockMovement
    tx.status = "paid"
    tx.paid_at = datetime.utcnow()

    for it in tx.items:
        if it.menu_item_id is None:
            continue
        m = await session.get(MenuItem, it.menu_item_id)
        if m is None:
            continue
        m.stock_qty -= it.quantity
        session.add(StockMovement(
            tenant_id=tenant_id, menu_item_id=it.menu_item_id,
            delta=-it.quantity, reason="sale",
            ref_type="transaction", ref_id=tx.id,
        ))

    await audit.write(
        session, tenant_id=tenant_id,
        action="tx.paid", entity="transaction", entity_id=tx.id,
        meta={"via": via, "bill_id": raw.get("id")},
    )
    await ws_hub.broadcast(tenant_id, "tx_paid", {
        "tx_id": tx.id, "tx_number": tx.tx_number,
        "total": str(tx.total), "via": via,
    })

    # Auto-email receipt when a customer is attached (Phase 14 #89 end-to-end).
    # Best-effort: if rendering or sending fails we don't fail the webhook;
    # the cashier can manually resend via POST /receipts/{id}/email.
    if tx.customer_id is not None:
        try:
            from app.models import Customer
            from app.routers.receipts import _ensure_pdf
            from app.services.email_resend import ResendDisabled, send_receipt

            cust = await session.get(Customer, tx.customer_id)
            if cust and cust.email:
                r = await _ensure_pdf(session, tx, tenant_id)
                from pathlib import Path as _P
                abs_path = _P(__file__).resolve().parent.parent.parent / r.pdf_path.lstrip("/")
                try:
                    msg_id = send_receipt(
                        to_email=cust.email,
                        subject=f"Receipt {tx.tx_number}",
                        html=f"<p>Receipt <b>{tx.tx_number}</b> attached. Total RM {tx.total}.</p>",
                        pdf_path=abs_path,
                    )
                    r.emailed_to = cust.email
                    r.emailed_at = datetime.utcnow()
                    r.resend_id = msg_id
                except ResendDisabled:
                    pass  # no Resend key — skip silently
                except Exception as e:
                    # Log to audit but don't fail the webhook.
                    await audit.write(
                        session, tenant_id=tenant_id,
                        action="receipt.email.fail",
                        entity="transaction", entity_id=tx.id,
                        meta={"error": str(e)[:200]},
                    )
        except Exception:
            pass  # never let auto-email block the paid path
