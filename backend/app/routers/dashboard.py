"""Phase 11: dashboard, forecast, reports, LLM ask."""
import csv
import io
import os
from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import Principal, get_session, require_role
from app.models import MenuItem, StockMovement, Transaction, TransactionItem
from app.services import anomaly as anomaly_svc
from app.services import forecast as fc_svc
from app.services import reorder as reo_svc

router = APIRouter(tags=["dashboard"])


# -------- Dashboard aggregates --------

class DashboardOut(BaseModel):
    revenue_today: Decimal
    tx_count_today: int
    revenue_7d: Decimal
    low_stock_count: int
    top_items_7d: list[dict]


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    today = date.today()
    start_today = datetime(today.year, today.month, today.day)
    start_7d = start_today - timedelta(days=7)

    rev_today = await session.scalar(
        select(func.coalesce(func.sum(Transaction.total), 0))
        .where(Transaction.status == "paid", Transaction.paid_at >= start_today)
    ) or Decimal("0")
    tx_today = await session.scalar(
        select(func.count(Transaction.id))
        .where(Transaction.status == "paid", Transaction.paid_at >= start_today)
    ) or 0
    rev_7d = await session.scalar(
        select(func.coalesce(func.sum(Transaction.total), 0))
        .where(Transaction.status == "paid", Transaction.paid_at >= start_7d)
    ) or Decimal("0")

    low = await session.scalar(
        select(func.count(MenuItem.id))
        .where(MenuItem.is_active == True,  # noqa: E712
               MenuItem.stock_qty <= MenuItem.reorder_point)
    ) or 0

    top = (await session.execute(
        select(MenuItem.name, func.sum(TransactionItem.quantity).label("units"))
        .join(TransactionItem, TransactionItem.menu_item_id == MenuItem.id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .where(Transaction.status == "paid", Transaction.paid_at >= start_7d)
        .group_by(MenuItem.name)
        .order_by(func.sum(TransactionItem.quantity).desc())
        .limit(5)
    )).all()

    return DashboardOut(
        revenue_today=Decimal(str(rev_today)),
        tx_count_today=int(tx_today),
        revenue_7d=Decimal(str(rev_7d)),
        low_stock_count=int(low),
        top_items_7d=[{"name": r[0], "units": int(r[1])} for r in top],
    )


# -------- Forecast per item --------

async def _daily_units(session: AsyncSession, menu_item_id: int, days: int = 14) -> list[float]:
    start = datetime.utcnow() - timedelta(days=days)
    rows = (await session.execute(
        select(
            func.date_trunc("day", Transaction.paid_at).label("d"),
            func.sum(TransactionItem.quantity),
        )
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .where(
            TransactionItem.menu_item_id == menu_item_id,
            Transaction.status == "paid",
            Transaction.paid_at >= start,
        )
        .group_by(func.date_trunc("day", Transaction.paid_at))
        .order_by(func.date_trunc("day", Transaction.paid_at))
    )).all()
    series = {r[0].date(): int(r[1]) for r in rows}
    out: list[float] = []
    for i in range(days, 0, -1):
        d = (datetime.utcnow() - timedelta(days=i)).date()
        out.append(float(series.get(d, 0)))
    return out


class ForecastRow(BaseModel):
    menu_item_id: int
    name: str
    daily_forecast: float
    reorder_point: float
    eoq: int
    anomaly_z: float
    is_anomaly: bool


@router.get("/forecast", response_model=list[ForecastRow])
async def forecast_all(
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    items = (await session.scalars(
        select(MenuItem).where(MenuItem.is_active == True)  # noqa: E712
        .order_by(MenuItem.name)
    )).all()
    out: list[ForecastRow] = []
    for m in items:
        series = await _daily_units(session, m.id, days=14)
        daily = fc_svc.forecast_daily(series)
        ropt = fc_svc.reorder_point(series)
        annual_demand = daily * 365
        q = reo_svc.eoq(annual_demand)
        z, flag = anomaly_svc.zscore_flag(series)
        out.append(ForecastRow(
            menu_item_id=m.id, name=m.name,
            daily_forecast=round(daily, 2),
            reorder_point=round(ropt, 2),
            eoq=q, anomaly_z=round(z, 2), is_anomaly=flag,
        ))
    return out


# -------- Reports (CSV only — XLSX/PDF can be added similarly) --------

@router.get("/reports/sales.csv")
async def report_sales_csv(
    days: int = Query(30, ge=1, le=365),
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    start = datetime.utcnow() - timedelta(days=days)
    rows = (await session.execute(
        select(
            Transaction.tx_number, Transaction.created_at, Transaction.status,
            Transaction.total, Transaction.payment_method,
        )
        .where(Transaction.created_at >= start)
        .order_by(Transaction.created_at)
    )).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["tx_number", "created_at", "status", "total", "payment_method"])
    for r in rows:
        w.writerow([r[0], r[1].isoformat(), r[2], f"{r[3]}", r[4]])
    data = buf.getvalue().encode("utf-8")
    return StreamingResponse(
        iter([data]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="sales_{days}d.csv"'},
    )


@router.get("/reports/inventory.csv")
async def report_inventory_csv(
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    items = (await session.scalars(
        select(MenuItem).where(MenuItem.is_active == True)  # noqa: E712
        .order_by(MenuItem.name)
    )).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "name", "stock_qty", "reorder_point", "avg_cost", "price"])
    for m in items:
        w.writerow([m.id, m.name, m.stock_qty, m.reorder_point, f"{m.avg_cost}", f"{m.price}"])
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8")]), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="inventory.csv"'},
    )


@router.get("/reports/audit.csv")
async def report_audit_csv(
    days: int = Query(7, ge=1, le=365),
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    from app.models import AuditLog

    start = datetime.utcnow() - timedelta(days=days)
    rows = (await session.execute(
        select(AuditLog.created_at, AuditLog.action, AuditLog.entity,
               AuditLog.entity_id, AuditLog.user_id, AuditLog.meta)
        .where(AuditLog.created_at >= start)
        .order_by(AuditLog.created_at.desc())
    )).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["created_at", "action", "entity", "entity_id", "user_id", "meta"])
    for r in rows:
        w.writerow([r[0].isoformat(), r[1], r[2], r[3], r[4], r[5]])
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8")]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audit_{days}d.csv"'},
    )


@router.get("/reports/stock-movements.csv")
async def report_stock_csv(
    days: int = Query(30, ge=1, le=365),
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    start = datetime.utcnow() - timedelta(days=days)
    rows = (await session.execute(
        select(StockMovement.created_at, MenuItem.name, StockMovement.delta,
               StockMovement.reason, StockMovement.ref_type, StockMovement.ref_id,
               StockMovement.note)
        .join(MenuItem, MenuItem.id == StockMovement.menu_item_id, isouter=True)
        .where(StockMovement.created_at >= start)
        .order_by(StockMovement.created_at.desc())
    )).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["created_at", "item", "delta", "reason", "ref_type", "ref_id", "note"])
    for r in rows:
        w.writerow([r[0].isoformat(), r[1] or "-", r[2], r[3], r[4] or "", r[5] or "", r[6] or ""])
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8")]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="stock_{days}d.csv"'},
    )


# -------- LLM ask (Ollama) --------

class AskBody(BaseModel):
    question: str


class AskOut(BaseModel):
    answer: str
    kpi: dict


@router.post("/ask", response_model=AskOut)
async def ask(
    body: AskBody,
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    # Pull the same KPIs the dashboard uses so the answer can cite them.
    kpi_model = await dashboard(p=p, session=session)  # type: ignore[arg-type]
    kpi = kpi_model.model_dump()

    prompt = (
        "You are a business assistant for a small retail shop.\n"
        f"KPIs:\n"
        f"- Revenue today: RM {kpi['revenue_today']}\n"
        f"- Transactions today: {kpi['tx_count_today']}\n"
        f"- Revenue last 7 days: RM {kpi['revenue_7d']}\n"
        f"- Items at/below reorder point: {kpi['low_stock_count']}\n"
        f"- Top items (7d): {kpi['top_items_7d']}\n\n"
        f"Question: {body.question}\n"
        "Answer in 1-3 short sentences, citing the numbers above where relevant."
    )

    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "phi3:mini")
    try:
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.post(f"{base}/api/generate", json={
                "model": model, "prompt": prompt, "stream": False,
            })
            r.raise_for_status()
            answer = r.json().get("response", "").strip() or "(empty response from Ollama)"
    except Exception as e:
        answer = f"(LLM unavailable: {e})"
    return AskOut(answer=answer, kpi=kpi)
