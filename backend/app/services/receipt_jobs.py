"""Phase 9 — RQ job: render receipt PDF + send via Resend (sync DB session)."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import DATABASE_URL, UPLOADS_DIR
from app.models.menu_item import MenuItem
from app.models.receipt import Receipt
from app.models.tenant import Tenant
from app.models.tenant_settings import TenantSettings
from app.models.transaction import Transaction, TransactionItem
from app.services.receipt_pdf import render_receipt
from app.services.resend_mailer import send_receipt_email


def _sync_url() -> str:
    u = DATABASE_URL
    return u.replace("postgresql+asyncpg", "postgresql+psycopg") if "+asyncpg" in u else u


def send_receipt_for_tx(tenant_id: int, tx_id: int) -> Optional[str]:
    """Called by RQ worker. Renders PDF, emails tx.receipt_email (if set), persists Receipt row."""
    engine = create_engine(_sync_url(), future=True)
    with Session(engine) as session:
        tx = session.execute(select(Transaction).where(
            Transaction.id == tx_id, Transaction.tenant_id == tenant_id
        )).scalars().first()
        if not tx:
            return None

        tenant = session.execute(select(Tenant).where(Tenant.id == tenant_id)).scalars().first()
        ts = session.execute(select(TenantSettings).where(
            TenantSettings.tenant_id == tenant_id
        )).scalars().first()
        items = session.execute(select(TransactionItem).where(
            TransactionItem.transaction_id == tx.id
        )).scalars().all()

        line_items = []
        for ti in items:
            name = "Unknown"
            if ti.menu_item_id:
                m = session.execute(select(MenuItem).where(MenuItem.id == ti.menu_item_id)).scalars().first()
                if m:
                    name = m.name
            line_items.append({
                "name": name, "qty": ti.quantity,
                "unit_price": ti.unit_price,
                "total": Decimal(ti.unit_price) * ti.quantity,
            })

        to: Optional[str] = tx.receipt_email

        logo_path: Optional[Path] = None
        if ts and ts.logo_path:
            rel = ts.logo_path.lstrip("/").replace("uploads/", "", 1)
            logo_path = UPLOADS_DIR / rel

        out_path = UPLOADS_DIR / str(tenant_id) / "receipts" / f"{tx.id}.pdf"
        render_receipt(
            tx_number=tx.tx_number,
            paid_at=tx.paid_at.strftime("%Y-%m-%d %H:%M") if tx.paid_at else None,
            cashier="—",
            recipient_email=to,
            shop_name=tenant.name if tenant else "Shop",
            shop_email=(ts.shop_contact_email if ts else None),
            shop_phone=(ts.shop_contact_phone if ts else None),
            logo_path=logo_path,
            line_items=line_items,
            total=tx.total,
            payment=f"{(tx.payment_method or '').upper()} · {tx.payment_ref or ''}",
            footer=(ts.receipt_footer if ts and ts.receipt_footer else "Thank you!"),
            out_path=out_path,
        )

        r = session.execute(select(Receipt).where(Receipt.transaction_id == tx.id)).scalars().first()
        if r is None:
            r = Receipt(tenant_id=tenant_id, transaction_id=tx.id, pdf_path=str(out_path))
            session.add(r)
        else:
            r.pdf_path = str(out_path)

        msg_id: Optional[str] = None
        if to:
            shop_name = tenant.name if tenant else "Your shop"
            html = (f"<p>Hi,</p><p>Your receipt for transaction <b>{tx.tx_number}</b> "
                    f"from <b>{shop_name}</b> is attached.</p><p>Thanks!</p>")
            msg_id = send_receipt_email(
                to=to, subject=f"Receipt {tx.tx_number} — {shop_name}",
                html=html, attachment_path=out_path, filename=f"{tx.tx_number}.pdf",
            )
            r.emailed_to = to
            r.emailed_at = datetime.utcnow()
            r.resend_id = msg_id

        session.commit()
        return msg_id
