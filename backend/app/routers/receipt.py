"""Phase 9 — receipt PDF + email send."""
import base64
import os
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Optional

import qrcode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import tenant_context
from app.config import BASE_DIR, UPLOADS_DIR
from app.deps import get_current_user, get_session, get_tenant
from app.models.menu_item import MenuItem
from app.models.receipt import Receipt
from app.models.tenant import Tenant
from app.models.tenant_settings import TenantSettings
from app.models.transaction import Transaction, TransactionItem
from app.models.user import User
from app.security import decode_token, issue_receipt_token
from app.services.audit import audit
from app.services.receipt_pdf import render_receipt
from app.services.resend_mailer import send_receipt_email

router = APIRouter(prefix="/receipts", tags=["receipts"])


class EmailIn(BaseModel):
    to: Optional[EmailStr] = None  # if None, uses tx.receipt_email (typed at checkout)


async def _build_receipt_pdf(session: AsyncSession, tenant_id: int, tx: Transaction) -> Path:
    tenant = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalars().first()
    ts = (await session.execute(select(TenantSettings).where(TenantSettings.tenant_id == tenant_id))).scalars().first()
    items = (await session.execute(select(TransactionItem).where(TransactionItem.transaction_id == tx.id))).scalars().all()

    line_items: list[dict] = []
    for ti in items:
        name = "Unknown"
        if ti.menu_item_id:
            m = (await session.execute(select(MenuItem).where(MenuItem.id == ti.menu_item_id))).scalars().first()
            if m:
                name = m.name
        line_items.append({
            "name": name,
            "qty": ti.quantity,
            "unit_price": ti.unit_price,
            "total": Decimal(ti.unit_price) * ti.quantity,
        })

    cashier_label = "—"
    if tx.staff_id:
        u = (await session.execute(select(User).where(User.id == tx.staff_id))).scalars().first()
        if u:
            cashier_label = u.username

    logo_path = None
    if ts and ts.logo_path:
        rel = ts.logo_path.lstrip("/").replace("uploads/", "", 1)
        logo_path = UPLOADS_DIR / rel

    out_dir = UPLOADS_DIR / str(tenant_id) / "receipts"
    out_path = out_dir / f"{tx.id}.pdf"

    render_receipt(
        tx_number=tx.tx_number,
        paid_at=tx.paid_at.strftime("%Y-%m-%d %H:%M") if tx.paid_at else None,
        cashier=cashier_label,
        recipient_email=tx.receipt_email,
        shop_name=tenant.name if tenant else "Shop",
        shop_email=(ts.shop_contact_email if ts else None),
        shop_phone=(ts.shop_contact_phone if ts else None),
        logo_path=logo_path,
        line_items=line_items,
        total=tx.total,
        payment=f"{tx.payment_method.upper()} · {tx.payment_ref or ''}",
        footer=(ts.receipt_footer if ts and ts.receipt_footer else "Thank you!"),
        out_path=out_path,
    )
    return out_path


@router.get("/{tx_id}/pdf")
async def get_pdf(
    tx_id: int,
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
):
    tx = (await session.execute(select(Transaction).where(Transaction.id == tx_id))).scalars().first()
    if not tx:
        raise HTTPException(status_code=404, detail="transaction not found")
    path = await _build_receipt_pdf(session, tenant_id, tx)

    r = (await session.execute(select(Receipt).where(Receipt.transaction_id == tx.id))).scalars().first()
    if r is None:
        session.add(Receipt(tenant_id=tenant_id, transaction_id=tx.id, pdf_path=str(path)))
        await session.commit()
    else:
        r.pdf_path = str(path)
        await session.commit()

    return FileResponse(path, media_type="application/pdf", filename=f"{tx.tx_number}.pdf")


@router.get("/{tx_id}/qr")
async def get_receipt_qr(
    tx_id: int,
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """QR code encoding the digital receipt PDF URL, for customer scan."""
    tx = (await session.execute(select(Transaction).where(Transaction.id == tx_id))).scalars().first()
    if not tx:
        raise HTTPException(status_code=404, detail="transaction not found")
    if tx.status != "paid":
        raise HTTPException(status_code=400, detail="digital receipt only available for paid transactions")

    public_base = os.getenv("PUBLIC_API_BASE", "https://api.geyam.com")
    token = issue_receipt_token(tenant_id=tenant_id, tx_id=tx_id)
    pdf_url = f"{public_base}/receipts/public?token={token}"
    img = qrcode.make(pdf_url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    qr_png = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return {"qr_png": qr_png, "pdf_url": pdf_url, "tx_number": tx.tx_number}


@router.get("/public")
async def get_public_receipt(
    token: str,
    session: AsyncSession = Depends(get_session),
):
    """Public endpoint reached by scanning the receipt QR.
    The signed token embedded in the URL authorizes read-only access to
    exactly one receipt PDF for 30 days. No login required."""
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid or expired receipt token")
    if payload.get("type") != "receipt":
        raise HTTPException(status_code=401, detail="wrong token type")
    tenant_id = payload.get("tenant_id")
    tx_id = payload.get("tx_id")
    if not isinstance(tenant_id, int) or not isinstance(tx_id, int):
        raise HTTPException(status_code=401, detail="malformed receipt token")

    tenant_context.set_current_tenant_id(tenant_id)

    tx = (await session.execute(select(Transaction).where(Transaction.id == tx_id))).scalars().first()
    if not tx:
        raise HTTPException(status_code=404, detail="transaction not found")
    if tx.status != "paid":
        raise HTTPException(status_code=400, detail="receipt only available for paid transactions")

    path = await _build_receipt_pdf(session, tenant_id, tx)
    return FileResponse(path, media_type="application/pdf", filename=f"{tx.tx_number}.pdf")


@router.post("/{tx_id}/email")
async def email_receipt(
    tx_id: int,
    body: EmailIn,
    user_claims: dict = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tx = (await session.execute(select(Transaction).where(Transaction.id == tx_id))).scalars().first()
    if not tx:
        raise HTTPException(status_code=404, detail="transaction not found")

    to = body.to or tx.receipt_email
    if not to:
        raise HTTPException(status_code=400, detail="no recipient (pass 'to' or set receipt_email on the transaction)")

    path = await _build_receipt_pdf(session, tenant_id, tx)
    tenant = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalars().first()
    shop_name = tenant.name if tenant else "Your shop"
    html = f"<p>Hi,</p><p>Your receipt for transaction <b>{tx.tx_number}</b> from <b>{shop_name}</b> is attached.</p><p>Thanks!</p>"

    msg_id = send_receipt_email(
        to=to, subject=f"Receipt {tx.tx_number} — {shop_name}",
        html=html, attachment_path=path, filename=f"{tx.tx_number}.pdf",
    )

    r = (await session.execute(select(Receipt).where(Receipt.transaction_id == tx.id))).scalars().first()
    if r is None:
        r = Receipt(tenant_id=tenant_id, transaction_id=tx.id, pdf_path=str(path))
        session.add(r)
    r.emailed_to = to
    r.emailed_at = datetime.utcnow()
    r.resend_id = msg_id

    await audit(session, action="tx.pay", tenant_id=tenant_id,
                user_id=user_claims.get("user_id"), entity="transaction", entity_id=tx.id,
                meta={"action": "receipt_email", "to": to, "msg_id": msg_id})
    await session.commit()
    return {"status": "ok", "to": to, "msg_id": msg_id}
