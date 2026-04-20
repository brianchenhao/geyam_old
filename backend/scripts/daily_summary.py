"""Phase 15 #92: daily KPI email digest sent to each tenant owner.

Run once per day from Task Scheduler / cron:
    python scripts/daily_summary.py

Queries the same aggregates the dashboard uses, renders a minimal HTML body,
sends via Resend (RESEND_API_KEY required). Skips tenants without an owner_email.
"""
import asyncio
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal, current_tenant_id  # noqa: E402
from app.models import MenuItem, Tenant, Transaction, TransactionItem  # noqa: E402


async def _build_payload(session, tenant_id: int) -> dict:
    today = date.today()
    start_today = datetime(today.year, today.month, today.day)
    start_7d = start_today - timedelta(days=7)

    rev = await session.scalar(
        select(func.coalesce(func.sum(Transaction.total), 0))
        .where(Transaction.status == "paid", Transaction.paid_at >= start_today)
    ) or Decimal("0")
    n = await session.scalar(
        select(func.count(Transaction.id))
        .where(Transaction.status == "paid", Transaction.paid_at >= start_today)
    ) or 0
    low = await session.scalar(
        select(func.count(MenuItem.id))
        .where(MenuItem.is_active == True,  # noqa: E712
               MenuItem.stock_qty <= MenuItem.reorder_point)
    ) or 0
    top = (await session.execute(
        select(MenuItem.name, func.sum(TransactionItem.quantity))
        .join(TransactionItem, TransactionItem.menu_item_id == MenuItem.id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .where(Transaction.status == "paid", Transaction.paid_at >= start_7d)
        .group_by(MenuItem.name)
        .order_by(func.sum(TransactionItem.quantity).desc()).limit(5)
    )).all()
    return {
        "revenue_today": rev, "tx_today": n,
        "low_stock": low, "top_items": top,
    }


def _html(tenant: Tenant, k: dict) -> str:
    rows = "".join(
        f"<tr><td>{name}</td><td align='right'>{units}</td></tr>"
        for name, units in k["top_items"]
    ) or "<tr><td colspan='2'><em>No paid sales in the last 7 days</em></td></tr>"
    return f"""\
<h2>{tenant.name} — daily summary</h2>
<ul>
  <li><b>Revenue today:</b> RM {k["revenue_today"]}</li>
  <li><b>Paid transactions today:</b> {k["tx_today"]}</li>
  <li><b>Items at or below reorder point:</b> {k["low_stock"]}</li>
</ul>
<h3>Top items (last 7 days)</h3>
<table border='1' cellpadding='6' cellspacing='0'>{rows}</table>
"""


async def main() -> None:
    from resend import Emails
    import resend

    key = os.getenv("RESEND_API_KEY")
    if not key:
        print("! RESEND_API_KEY not set — nothing sent")
        return
    resend.api_key = key
    from_addr = os.getenv("RESEND_FROM", "noreply@geyam.com")

    async with SessionLocal() as s:
        tenants = (await s.scalars(
            select(Tenant).where(Tenant.is_active == True)  # noqa: E712
            .execution_options(skip_tenant_filter=True)
        )).all()
        for t in tenants:
            if not t.owner_email:
                continue
            tok = current_tenant_id.set(t.id)
            try:
                payload = await _build_payload(s, t.id)
            finally:
                current_tenant_id.reset(tok)
            html = _html(t, payload)
            try:
                res = Emails.send({
                    "from": from_addr,
                    "to": [t.owner_email],
                    "subject": f"{t.name} — daily summary",
                    "html": html,
                })
                print(f"+ sent to {t.owner_email} (id={res.get('id')})")
            except Exception as e:
                print(f"! send failed for {t.owner_email}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
