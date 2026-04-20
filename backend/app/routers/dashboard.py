"""Phase 11 — dashboard KPIs, forecast, reports, /ask."""
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_session, get_tenant, require_role
from app.models.menu_item import MenuItem
from app.models.stock_movement import StockMovement
from app.models.transaction import Transaction, TransactionItem
from app.models.user import User
from app.services.forecast import (daily_series_from_rows, eoq, ewma,
                                     reorder_point, safety_stock, z_score_anomaly)
from app.services.ollama_ask import ask as ollama_ask

router = APIRouter(tags=["dashboard"])


def _range_for(range_key: Optional[str], frm: Optional[date], to: Optional[date]) -> tuple[datetime, datetime]:
    today = date.today()
    if range_key == "7d":
        start = today - timedelta(days=6)
    elif range_key == "30d":
        start = today - timedelta(days=29)
    elif range_key == "today" or range_key is None and frm is None:
        start = today
    elif frm is not None:
        start = frm
    else:
        start = today
    end = to or today
    return datetime.combine(start, datetime.min.time()), datetime.combine(end, datetime.max.time())


class DashboardOut(BaseModel):
    range: str
    revenue: Decimal
    tx_count: int
    avg_basket: Decimal
    top_item: Optional[str] = None
    low_stock: list[dict]
    staff_performance: list[dict]
    recent_transactions: list[dict]
    source_breakdown: dict[str, int]
    anomaly_z: float


@router.get("/dashboard", dependencies=[Depends(require_role("owner"))])
async def dashboard(
    range: Literal["today", "7d", "30d", "custom"] = "today",
    frm: Optional[date] = Query(default=None, alias="from"),
    to: Optional[date] = Query(default=None),
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> DashboardOut:
    start, end = _range_for(range, frm, to)

    tx_rows = (await session.execute(
        select(Transaction).where(
            Transaction.status == "paid",
            Transaction.paid_at >= start, Transaction.paid_at <= end,
        ).order_by(Transaction.paid_at.desc())
    )).scalars().all()

    revenue = sum((t.total for t in tx_rows), Decimal("0"))
    tx_count = len(tx_rows)
    avg_basket = (revenue / tx_count) if tx_count else Decimal("0")

    # Top item + source breakdown
    top_counter: Counter[int] = Counter()
    source_counter: Counter[str] = Counter()
    for tx in tx_rows:
        items = (await session.execute(select(TransactionItem).where(TransactionItem.transaction_id == tx.id))).scalars().all()
        for ti in items:
            if ti.menu_item_id:
                top_counter[ti.menu_item_id] += ti.quantity or 0
            if ti.source:
                source_counter[ti.source] += 1

    top_name = None
    if top_counter:
        best_id, _ = top_counter.most_common(1)[0]
        m = (await session.execute(select(MenuItem).where(MenuItem.id == best_id))).scalars().first()
        top_name = m.name if m else None

    low_stock_rows = (await session.execute(
        select(MenuItem).where(MenuItem.is_active.is_(True)).order_by(MenuItem.name)
    )).scalars().all()
    low_stock = [
        {"id": m.id, "name": m.name, "stock_qty": m.stock_qty or 0,
         "reorder_point": m.reorder_point or 0}
        for m in low_stock_rows if (m.stock_qty or 0) <= (m.reorder_point or 0)
    ]

    # Staff performance (count + revenue by staff_id)
    staff_counter: dict[int, tuple[int, Decimal]] = {}
    for tx in tx_rows:
        if tx.staff_id:
            c, r = staff_counter.get(tx.staff_id, (0, Decimal("0")))
            staff_counter[tx.staff_id] = (c + 1, r + tx.total)
    staff_performance: list[dict] = []
    for sid, (c, r) in staff_counter.items():
        u = (await session.execute(select(User).where(User.id == sid))).scalars().first()
        staff_performance.append({
            "staff_id": sid,
            "username": u.username if u else "?",
            "tx_count": c,
            "revenue": r,
        })

    recent = [
        {"id": tx.id, "tx_number": tx.tx_number, "total": tx.total,
         "staff_id": tx.staff_id, "paid_at": tx.paid_at}
        for tx in tx_rows[:10]
    ]

    # Anomaly (z-score of today revenue vs trailing 30 days)
    today = date.today()
    rows_30 = (await session.execute(
        select(Transaction.paid_at, Transaction.total).where(
            Transaction.status == "paid",
            Transaction.paid_at >= datetime.combine(today - timedelta(days=29), datetime.min.time()),
            Transaction.paid_at <= datetime.combine(today, datetime.max.time()),
        )
    )).all()
    window = daily_series_from_rows([(r[0].date(), float(r[1])) for r in rows_30], 30)
    z = z_score_anomaly(window[-1], window[:-1])

    return DashboardOut(
        range=range, revenue=revenue, tx_count=tx_count, avg_basket=avg_basket,
        top_item=top_name, low_stock=low_stock,
        staff_performance=staff_performance, recent_transactions=recent,
        source_breakdown=dict(source_counter), anomaly_z=round(z, 2),
    )


@router.get("/dashboard/mobile", dependencies=[Depends(require_role("owner"))])
async def dashboard_mobile(tenant_id: int = Depends(get_tenant),
                             session: AsyncSession = Depends(get_session)) -> dict:
    """Slim version for the mobile owner light dashboard."""
    start, end = _range_for("today", None, None)
    tx_rows = (await session.execute(
        select(Transaction).where(
            Transaction.status == "paid",
            Transaction.paid_at >= start, Transaction.paid_at <= end,
        )
    )).scalars().all()
    revenue = sum((t.total for t in tx_rows), Decimal("0"))
    low_stock_count = (await session.execute(
        select(func.count()).select_from(MenuItem).where(
            MenuItem.is_active.is_(True),
            MenuItem.stock_qty <= MenuItem.reorder_point,
        )
    )).scalar() or 0
    return {"today_revenue": revenue, "today_tx": len(tx_rows),
            "low_stock_count": int(low_stock_count)}


@router.get("/forecast", dependencies=[Depends(require_role("owner"))])
async def forecast(tenant_id: int = Depends(get_tenant),
                    session: AsyncSession = Depends(get_session)) -> list[dict]:
    # 30-day daily demand per item, EWMA + SS + ROP + EOQ.
    items = (await session.execute(select(MenuItem).where(MenuItem.is_active.is_(True)))).scalars().all()
    since = datetime.combine(date.today() - timedelta(days=29), datetime.min.time())
    tx_items = (await session.execute(
        select(TransactionItem.menu_item_id, Transaction.paid_at, TransactionItem.quantity).join(
            Transaction, Transaction.id == TransactionItem.transaction_id
        ).where(Transaction.status == "paid", Transaction.paid_at >= since)
    )).all()

    by_item: dict[int, list[tuple[date, float]]] = {}
    for mid, pa, q in tx_items:
        if mid and pa:
            by_item.setdefault(mid, []).append((pa.date(), float(q or 0)))

    out: list[dict] = []
    for m in items:
        series = daily_series_from_rows(by_item.get(m.id, []), 30)
        e = ewma(series, 0.3)
        ss = safety_stock(series)
        rp = reorder_point(e, lead_time_days=7, ss=ss)
        annual = e * 365
        q = eoq(annual)
        out.append({
            "menu_item_id": m.id, "name": m.name,
            "ewma_daily": round(e, 2),
            "safety_stock": round(ss, 2),
            "reorder_point": round(rp, 1),
            "current_stock": m.stock_qty or 0,
            "eoq": q,
        })
    return out


@router.get("/reports", dependencies=[Depends(require_role("owner"))])
async def reports(
    format: Literal["csv", "json"] = "csv",
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export today's sales-by-day + item perf + inventory valuation."""
    since = datetime.combine(date.today() - timedelta(days=29), datetime.min.time())
    tx = (await session.execute(
        select(Transaction).where(Transaction.paid_at >= since, Transaction.status == "paid")
    )).scalars().all()
    by_day: dict[str, Decimal] = {}
    for t in tx:
        d = t.paid_at.strftime("%Y-%m-%d") if t.paid_at else "?"
        by_day[d] = by_day.get(d, Decimal("0")) + t.total

    items = (await session.execute(select(MenuItem).where(MenuItem.is_active.is_(True)))).scalars().all()
    valuation = sum(((m.stock_qty or 0) * (m.avg_cost or Decimal("0")) for m in items), Decimal("0"))

    if format == "json":
        return Response(
            content=str({"sales_by_day": {k: str(v) for k, v in by_day.items()},
                          "inventory_valuation": str(valuation)}).replace("'", '"'),
            media_type="application/json",
        )

    lines = ["date,revenue"]
    for d in sorted(by_day.keys()):
        lines.append(f"{d},{by_day[d]}")
    lines.append("")
    lines.append(f"inventory_valuation,{valuation}")
    return Response("\n".join(lines), media_type="text/csv")


class AskIn(BaseModel):
    question: str


@router.post("/ask", dependencies=[Depends(require_role("owner"))])
async def ask_endpoint(body: AskIn, tenant_id: int = Depends(get_tenant),
                        session: AsyncSession = Depends(get_session)) -> dict:
    # Build a tiny context from recent KPIs for the LLM
    start, end = _range_for("7d", None, None)
    tx = (await session.execute(
        select(Transaction).where(Transaction.status == "paid",
                                    Transaction.paid_at >= start, Transaction.paid_at <= end)
    )).scalars().all()
    revenue = sum((t.total for t in tx), Decimal("0"))
    context = f"Last 7 days: {len(tx)} paid transactions totaling RM {revenue:.2f}."
    answer = ollama_ask(body.question, context=context)
    return {"answer": answer, "context_used": context}
