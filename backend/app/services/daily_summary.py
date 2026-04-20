"""Phase 15 stretch — daily shop summary emailed to each owner.

Call once a day (cron or manual) with `python -m app.services.daily_summary`.
For each active tenant with an owner_email, composes:
  - yesterday's revenue + tx count + top 3 items
  - low-stock items (stock_qty <= reorder_point)
  - anomaly flag if z-score > 2
…and sends a single HTML email via Resend.
"""
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models.menu_item import MenuItem  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.transaction import Transaction, TransactionItem  # noqa: E402
from app.services.forecast import daily_series_from_rows, z_score_anomaly  # noqa: E402
from app.services.resend_mailer import send_receipt_email  # noqa: E402


def _sessionmaker():
    sync_url = os.environ.get("ALEMBIC_DATABASE_URL") or \
        os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql+psycopg")
    engine = create_engine(sync_url, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _summarize(session, tenant: Tenant) -> dict:
    yday = date.today() - timedelta(days=1)
    start = datetime.combine(yday, datetime.min.time())
    end = datetime.combine(yday, datetime.max.time())

    tx = session.execute(
        select(Transaction).where(
            Transaction.tenant_id == tenant.id,
            Transaction.status == "paid",
            Transaction.paid_at >= start, Transaction.paid_at <= end,
        )
    ).scalars().all()
    revenue = sum((t.total for t in tx), Decimal("0"))
    tx_count = len(tx)

    top: dict[int, int] = {}
    for t in tx:
        items = session.execute(
            select(TransactionItem).where(TransactionItem.transaction_id == t.id)
        ).scalars().all()
        for ti in items:
            if ti.menu_item_id is not None:
                top[ti.menu_item_id] = top.get(ti.menu_item_id, 0) + (ti.quantity or 0)
    top3_ids = sorted(top.items(), key=lambda kv: -kv[1])[:3]
    top3_names: list[tuple[str, int]] = []
    for mid, q in top3_ids:
        m = session.execute(select(MenuItem).where(MenuItem.id == mid)).scalars().first()
        if m:
            top3_names.append((m.name, q))

    low_rows = session.execute(
        select(MenuItem).where(MenuItem.tenant_id == tenant.id,
                                MenuItem.is_active.is_(True))
    ).scalars().all()
    low = [m for m in low_rows if (m.stock_qty or 0) <= (m.reorder_point or 0)]

    since = datetime.combine(date.today() - timedelta(days=29), datetime.min.time())
    rows_30 = session.execute(
        select(Transaction.paid_at, Transaction.total).where(
            Transaction.tenant_id == tenant.id,
            Transaction.status == "paid",
            Transaction.paid_at >= since,
        )
    ).all()
    window = daily_series_from_rows([(r[0].date(), float(r[1])) for r in rows_30], 30)
    z = z_score_anomaly(float(revenue), window[:-1]) if tx_count else 0.0

    return {
        "tenant": tenant,
        "date": yday,
        "revenue": revenue,
        "tx_count": tx_count,
        "top3": top3_names,
        "low_stock": low,
        "z": z,
    }


def _render_html(s: dict) -> str:
    tenant = s["tenant"]
    lines = [
        f"<h2>{tenant.name} — {s['date'].strftime('%A, %d %b %Y')}</h2>",
        f"<p>Yesterday: <b>RM {s['revenue']:.2f}</b> across <b>{s['tx_count']}</b> transactions.</p>",
    ]
    if s["z"] > 2:
        lines.append("<p style='color:#c00'>⚠ Unusually high day (z-score > 2).</p>")
    elif s["z"] < -2:
        lines.append("<p style='color:#c00'>⚠ Unusually quiet day (z-score < -2).</p>")
    if s["top3"]:
        lines.append("<h3>Top items</h3><ol>")
        for name, q in s["top3"]:
            lines.append(f"<li>{name} — {q} sold</li>")
        lines.append("</ol>")
    if s["low_stock"]:
        lines.append("<h3>Low stock (≤ reorder point)</h3><ul>")
        for m in s["low_stock"][:10]:
            lines.append(f"<li>{m.name}: {m.stock_qty} (reorder at {m.reorder_point})</li>")
        lines.append("</ul>")
    if not s["tx_count"] and not s["low_stock"]:
        lines.append("<p>Nothing notable yesterday. Have a great day!</p>")
    lines.append("<p style='color:#888;font-size:11px'>— GEYAM daily summary</p>")
    return "\n".join(lines)


def run_for_all_tenants() -> list[dict]:
    Maker = _sessionmaker()
    results: list[dict] = []
    with Maker() as s:
        tenants = s.execute(
            select(Tenant).where(Tenant.is_active.is_(True))
        ).scalars().all()
        for t in tenants:
            summary = _summarize(s, t)
            html = _render_html(summary)
            msg_id = send_receipt_email(
                to=t.owner_email,
                subject=f"GEYAM summary — {t.name} — {summary['date'].strftime('%d %b')}",
                html=html,
            )
            results.append({"tenant": t.handle, "to": t.owner_email, "msg_id": msg_id,
                             "revenue": str(summary["revenue"]), "tx_count": summary["tx_count"]})
            print(f"[summary] {t.handle} -> {t.owner_email} tx={summary['tx_count']} revenue=RM {summary['revenue']} msg_id={msg_id}")
    return results


if __name__ == "__main__":
    rows = run_for_all_tenants()
    print(f"sent {len(rows)} summaries")
