"""Phase 9 — render PDFs, email via Resend."""
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import Principal, get_session, require_role
from app.models import (
    Customer,
    MenuItem,
    Receipt,
    Tenant,
    TenantSettings,
    Transaction,
    TransactionItem,
)
from app.services import audit, receipt_pdf
from app.services.email_resend import ResendDisabled, send_receipt

router = APIRouter(prefix="/receipts", tags=["receipts"])

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


async def _ensure_pdf(session: AsyncSession, tx: Transaction, tenant_id: int) -> Receipt:
    """Render (or reuse) the receipt PDF for tx. Returns the Receipt row."""
    existing = await session.scalar(
        select(Receipt).where(Receipt.transaction_id == tx.id)
    )
    if existing and existing.pdf_path and (BACKEND_ROOT / existing.pdf_path.lstrip("/")).exists():
        return existing

    settings = await session.get(TenantSettings, tenant_id)
    tenant = await session.scalar(
        select(Tenant).where(Tenant.id == tenant_id)
        .execution_options(skip_tenant_filter=True)
    )

    items_rows = (await session.scalars(
        select(TransactionItem).where(TransactionItem.transaction_id == tx.id)
    )).all()
    items_out = []
    for it in items_rows:
        if it.menu_item_id is None:
            items_out.append({"name": "Manual", "qty": it.quantity, "unit_price": it.unit_price})
            continue
        m = await session.get(MenuItem, it.menu_item_id)
        items_out.append({
            "name": m.name if m else "?",
            "qty": it.quantity,
            "unit_price": it.unit_price,
        })

    out_rel = Path("uploads") / str(tenant_id) / "receipts" / f"{tx.tx_number}.pdf"
    out_abs = BACKEND_ROOT / out_rel
    logo_abs = None
    if settings and settings.logo_path:
        logo_abs = BACKEND_ROOT / settings.logo_path.lstrip("/")
    receipt_pdf.render(
        out_path=out_abs,
        shop_name=tenant.name if tenant else "GEYAM",
        tx_number=tx.tx_number,
        created_at=tx.paid_at or tx.created_at,
        items=items_out,
        total=tx.total,
        footer=(settings.receipt_footer if settings else "Thank you!"),
        contact_email=settings.shop_contact_email if settings else None,
        contact_phone=settings.shop_contact_phone if settings else None,
        logo_abs_path=logo_abs if logo_abs and logo_abs.exists() else None,
    )

    if existing:
        existing.pdf_path = "/" + str(out_rel).replace("\\", "/")
        return existing
    r = Receipt(
        tenant_id=tenant_id,
        transaction_id=tx.id,
        pdf_path="/" + str(out_rel).replace("\\", "/"),
    )
    session.add(r)
    await session.flush()
    return r


@router.get("/{tx_id}/pdf")
async def get_pdf(
    tx_id: int,
    p: Principal = Depends(require_role("owner", "cashier")),
    session: AsyncSession = Depends(get_session),
):
    tx = await session.get(Transaction, tx_id)
    if tx is None or tx.tenant_id != p.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    r = await _ensure_pdf(session, tx, p.tenant_id)
    await session.commit()
    abs_path = BACKEND_ROOT / r.pdf_path.lstrip("/")
    return FileResponse(str(abs_path), media_type="application/pdf",
                         filename=f"{tx.tx_number}.pdf")


class EmailBody(BaseModel):
    to: EmailStr | None = None  # override customer email if needed


@router.post("/{tx_id}/email")
async def email_receipt(
    tx_id: int,
    body: EmailBody,
    p: Principal = Depends(require_role("owner", "cashier")),
    session: AsyncSession = Depends(get_session),
):
    tx = await session.get(Transaction, tx_id)
    if tx is None or tx.tenant_id != p.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")

    to = str(body.to) if body.to else None
    if to is None and tx.customer_id:
        cust = await session.get(Customer, tx.customer_id)
        if cust and cust.email:
            to = cust.email
    if not to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no email address available")

    r = await _ensure_pdf(session, tx, p.tenant_id)
    abs_path = BACKEND_ROOT / r.pdf_path.lstrip("/")
    tenant = await session.scalar(
        select(Tenant).where(Tenant.id == p.tenant_id)
        .execution_options(skip_tenant_filter=True)
    )
    shop_name = tenant.name if tenant else "GEYAM"
    html = (
        f"<p>Thank you for your purchase at {shop_name}.</p>"
        f"<p>Your receipt <b>{tx.tx_number}</b> is attached. "
        f"Total: <b>RM {tx.total}</b>.</p>"
    )

    try:
        msg_id = send_receipt(
            to_email=to, subject=f"Receipt {tx.tx_number} — {shop_name}",
            html=html, pdf_path=abs_path,
        )
    except ResendDisabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "RESEND_API_KEY not set"
        )
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"send failed: {e}")

    r.emailed_to = to
    r.emailed_at = datetime.utcnow()
    r.resend_id = msg_id
    await audit.write(
        session, tenant_id=p.tenant_id, user_id=p.user_id,
        action="receipt.email", entity="transaction", entity_id=tx.id,
        meta={"to": to, "resend_id": msg_id},
    )
    await session.commit()
    return {"ok": True, "to": to, "resend_id": msg_id}
