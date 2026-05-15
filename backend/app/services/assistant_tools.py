"""Tool registry for the POS assistant (Qwen3.5 tool calling).

Each tool is a small, focused query. Return values are compact dicts —
the LLM paraphrases them for the user. No pie/line/series data.

Constraints per product spec:
- product_sales: aggregate totals only, NO list of items, NO pie-style data.
- day_by_day_revenue: summary stats only, NO daily series / line data.

Every tool accepts a sqlalchemy AsyncSession. Tools are tenant-scoped
automatically via the SQLAlchemy event hook (get_tenant set the context).
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Awaitable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.menu_item import MenuItem
from app.models.transaction import Transaction, TransactionItem
from app.models.user import User
from app.services.forecast import (daily_series_from_rows, ewma,
                                     reorder_point, safety_stock)


# ---------- helpers ----------

def _window(days: int) -> tuple[datetime, datetime]:
    today = date.today()
    start = datetime.combine(today - timedelta(days=max(days - 1, 0)), datetime.min.time())
    end = datetime.combine(today, datetime.max.time())
    return start, end


def _money(v: Decimal | float | int | None) -> float:
    if v is None:
        return 0.0
    return float(v)


# ---------- tool implementations ----------

async def product_sales_summary(session: AsyncSession, days: int = 7) -> dict:
    """Aggregate product-level sales for the last N days.
    Returns totals only — NO per-item list, NO pie data.
    """
    start, end = _window(days)
    rows = (await session.execute(
        select(TransactionItem.menu_item_id, TransactionItem.quantity, TransactionItem.unit_price)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .where(Transaction.status == "paid",
               Transaction.paid_at >= start, Transaction.paid_at <= end)
    )).all()

    total_units = 0
    total_rev = Decimal("0")
    item_rev: dict[int, Decimal] = {}
    item_qty: Counter[int] = Counter()
    for mid, qty, price in rows:
        q = qty or 0
        total_units += q
        line = (price or Decimal("0")) * q
        total_rev += line
        if mid:
            item_qty[mid] += q
            item_rev[mid] = item_rev.get(mid, Decimal("0")) + line

    top_name = None
    top_rev = 0.0
    if item_rev:
        best_id = max(item_rev, key=lambda k: item_rev[k])
        top_rev = _money(item_rev[best_id])
        m = (await session.execute(select(MenuItem).where(MenuItem.id == best_id))).scalars().first()
        top_name = m.name if m else f"#{best_id}"

    distinct = len(item_qty)
    avg_rev_per_product = _money(total_rev / distinct) if distinct else 0.0

    return {
        "window_days": days,
        "distinct_products_sold": distinct,
        "total_units_sold": int(total_units),
        "total_revenue": _money(total_rev),
        "avg_revenue_per_product": round(avg_rev_per_product, 2),
        "best_selling_product": top_name,
        "best_selling_product_revenue": round(top_rev, 2),
    }


async def day_by_day_revenue_summary(session: AsyncSession, days: int = 7) -> dict:
    """Revenue aggregates across the last N days.
    Returns summary stats only — NO daily series / line data.
    """
    start, end = _window(days)
    rows = (await session.execute(
        select(Transaction.paid_at, Transaction.total)
        .where(Transaction.status == "paid",
               Transaction.paid_at >= start, Transaction.paid_at <= end)
    )).all()

    by_day: dict[date, Decimal] = {}
    d = start.date()
    while d <= end.date():
        by_day[d] = Decimal("0")
        d += timedelta(days=1)
    for paid_at, total in rows:
        if paid_at:
            by_day[paid_at.date()] = by_day.get(paid_at.date(), Decimal("0")) + (total or Decimal("0"))

    if not by_day:
        return {"window_days": days, "total_revenue": 0.0, "avg_daily_revenue": 0.0,
                "best_day": None, "best_day_revenue": 0.0,
                "worst_day": None, "worst_day_revenue": 0.0,
                "days_with_sales": 0, "days_with_zero_sales": days}

    totals = list(by_day.values())
    total = sum(totals, Decimal("0"))
    avg = total / len(totals) if totals else Decimal("0")
    best_day = max(by_day, key=lambda k: by_day[k])
    worst_day = min(by_day, key=lambda k: by_day[k])
    zero_days = sum(1 for v in totals if v == 0)

    return {
        "window_days": days,
        "total_revenue": _money(total),
        "avg_daily_revenue": round(_money(avg), 2),
        "best_day": best_day.isoformat(),
        "best_day_revenue": _money(by_day[best_day]),
        "worst_day": worst_day.isoformat(),
        "worst_day_revenue": _money(by_day[worst_day]),
        "days_with_sales": len(totals) - zero_days,
        "days_with_zero_sales": zero_days,
    }


async def staff_performance(session: AsyncSession, days: int = 7) -> dict:
    """Per-staff transaction count and revenue for the last N days."""
    start, end = _window(days)
    rows = (await session.execute(
        select(Transaction.staff_id, Transaction.total)
        .where(Transaction.status == "paid",
               Transaction.paid_at >= start, Transaction.paid_at <= end)
    )).all()

    by_staff: dict[int, tuple[int, Decimal]] = {}
    for sid, total in rows:
        if sid is None:
            continue
        c, r = by_staff.get(sid, (0, Decimal("0")))
        by_staff[sid] = (c + 1, r + (total or Decimal("0")))

    staff_list: list[dict] = []
    for sid, (c, r) in by_staff.items():
        u = (await session.execute(select(User).where(User.id == sid))).scalars().first()
        staff_list.append({
            "username": u.username if u else f"#{sid}",
            "role": u.role if u else None,
            "tx_count": c,
            "revenue": _money(r),
        })
    staff_list.sort(key=lambda s: s["revenue"], reverse=True)

    top = staff_list[0] if staff_list else None
    return {
        "window_days": days,
        "staff_count": len(staff_list),
        "staff": staff_list,
        "top_staff_username": top["username"] if top else None,
        "top_staff_revenue": top["revenue"] if top else 0.0,
    }


async def low_stock_items(session: AsyncSession) -> dict:
    """Items at or below their reorder point."""
    items = (await session.execute(
        select(MenuItem).where(MenuItem.is_active.is_(True))
    )).scalars().all()
    low = [
        {"name": m.name, "stock_qty": m.stock_qty or 0,
         "reorder_point": m.reorder_point or 0}
        for m in items
        if (m.stock_qty or 0) <= (m.reorder_point or 0)
    ]
    low.sort(key=lambda r: r["stock_qty"])
    return {
        "low_stock_count": len(low),
        "total_active_items": len(items),
        "items": low,
    }


async def forecast_reorder(session: AsyncSession, lead_time_days: int = 7) -> dict:
    """Compute EWMA daily demand + reorder points.
    Returns only items that currently need reordering (stock <= ROP).
    """
    items = (await session.execute(
        select(MenuItem).where(MenuItem.is_active.is_(True))
    )).scalars().all()
    since = datetime.combine(date.today() - timedelta(days=29), datetime.min.time())
    ti_rows = (await session.execute(
        select(TransactionItem.menu_item_id, Transaction.paid_at, TransactionItem.quantity)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .where(Transaction.status == "paid", Transaction.paid_at >= since)
    )).all()

    by_item: dict[int, list[tuple[date, float]]] = {}
    for mid, pa, q in ti_rows:
        if mid and pa:
            by_item.setdefault(mid, []).append((pa.date(), float(q or 0)))

    needs_reorder: list[dict] = []
    for m in items:
        series = daily_series_from_rows(by_item.get(m.id, []), 30)
        e = ewma(series, 0.3)
        ss = safety_stock(series)
        rp = reorder_point(e, lead_time_days=lead_time_days, ss=ss)
        current = m.stock_qty or 0
        if current <= rp:
            needs_reorder.append({
                "name": m.name,
                "current_stock": current,
                "reorder_point": round(rp, 1),
                "avg_daily_sales": round(e, 2),
            })
    needs_reorder.sort(key=lambda r: r["current_stock"])

    return {
        "lead_time_days": lead_time_days,
        "items_needing_reorder": len(needs_reorder),
        "items": needs_reorder,
    }


async def detection_source_mix(session: AsyncSession, days: int = 7) -> dict:
    """Breakdown of detection sources (yolo vs mediapipe vs openai vs manual)."""
    start, end = _window(days)
    rows = (await session.execute(
        select(TransactionItem.source)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .where(Transaction.status == "paid",
               Transaction.paid_at >= start, Transaction.paid_at <= end)
    )).all()

    counter: Counter[str] = Counter()
    for (src,) in rows:
        counter[src or "manual"] += 1
    total = sum(counter.values())
    percentages = {k: round(100.0 * v / total, 1) if total else 0.0 for k, v in counter.items()}

    dominant = None
    if counter:
        dominant = counter.most_common(1)[0][0]

    return {
        "window_days": days,
        "total_detections": total,
        "counts": dict(counter),
        "percentages": percentages,
        "dominant_source": dominant,
    }


async def recent_transactions(session: AsyncSession, limit: int = 5) -> dict:
    """Most recent N paid transactions, newest first.
    Use for 'last transaction', 'latest sale', 'what just sold'.
    """
    limit = max(1, min(limit, 20))
    rows = (await session.execute(
        select(Transaction)
        .where(Transaction.status == "paid")
        .order_by(Transaction.paid_at.desc().nullslast())
        .limit(limit)
    )).scalars().all()

    tx_list: list[dict] = []
    for tx in rows:
        u = None
        if tx.staff_id:
            u = (await session.execute(select(User).where(User.id == tx.staff_id))).scalars().first()
        tx_list.append({
            "tx_number": tx.tx_number,
            "total": _money(tx.total),
            "paid_at": tx.paid_at.isoformat() if tx.paid_at else None,
            "staff": u.username if u else None,
            "payment_method": tx.payment_method,
        })

    return {
        "count": len(tx_list),
        "transactions": tx_list,
        "latest": tx_list[0] if tx_list else None,
    }


async def old_transactions(session: AsyncSession, older_than_days: int = 7) -> dict:
    """Transactions older than N days (default 7). Status breakdown + revenue."""
    cutoff = datetime.combine(date.today() - timedelta(days=older_than_days), datetime.min.time())
    rows = (await session.execute(
        select(Transaction.status, Transaction.total, Transaction.paid_at, Transaction.created_at)
        .where(Transaction.created_at < cutoff)
    )).all()

    status_counts: Counter[str] = Counter()
    paid_revenue = Decimal("0")
    oldest: datetime | None = None
    newest: datetime | None = None
    for status, total, paid_at, created_at in rows:
        status_counts[status] += 1
        if status == "paid":
            paid_revenue += (total or Decimal("0"))
        ref = paid_at or created_at
        if ref is not None:
            oldest = ref if oldest is None or ref < oldest else oldest
            newest = ref if newest is None or ref > newest else newest

    return {
        "cutoff_days": older_than_days,
        "cutoff_date": cutoff.date().isoformat(),
        "total_transactions": sum(status_counts.values()),
        "status_counts": dict(status_counts),
        "paid_revenue": _money(paid_revenue),
        "oldest_transaction_at": oldest.isoformat() if oldest else None,
        "newest_transaction_at": newest.isoformat() if newest else None,
    }


# ---------- tool registry + JSON schemas (Ollama tool format) ----------

ToolFn = Callable[..., Awaitable[dict]]

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "product_sales_summary",
            "description": (
                "Aggregate product-level sales totals for a recent window. "
                "Use for questions about product sales, units sold, best seller, "
                "product revenue. Returns totals and best-seller only (no per-item list)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Lookback window in days. Default 7.", "default": 7},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "day_by_day_revenue_summary",
            "description": (
                "Revenue aggregates across the last N days. Use for questions about "
                "total revenue, average daily revenue, best day, worst day, zero-sales days. "
                "Returns summary stats only, NOT a daily series."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Lookback window in days. Default 7.", "default": 7},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "staff_performance",
            "description": (
                "Per-staff transaction count and revenue for a recent window. "
                "Use for questions about cashier / staff performance, who sold the most, "
                "how each staff member is doing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Lookback window in days. Default 7.", "default": 7},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "low_stock_items",
            "description": (
                "List of menu items currently at or below their reorder point. "
                "Use for questions like 'what is running low', 'any stock alerts', "
                "'which items need restocking'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forecast_reorder",
            "description": (
                "Forecast-driven reorder list using EWMA daily demand and safety stock. "
                "Use for questions about forecasted demand, reorder points, what to purchase, "
                "purchase planning."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_time_days": {"type": "integer", "description": "Supplier lead time in days. Default 7.", "default": 7},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detection_source_mix",
            "description": (
                "Breakdown of how items were detected at POS checkout: YOLO (in-house), "
                "MediaPipe (fallback), OpenAI Vision (paid fallback), or manual. "
                "Use for questions about detection accuracy, OpenAI usage, ML reliance, "
                "how often the YOLO model is doing the work."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Lookback window in days. Default 7.", "default": 7},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recent_transactions",
            "description": (
                "Most recent N paid transactions, newest first. "
                "Use for questions like 'what was the last transaction', "
                "'latest sale', 'show me the most recent orders', 'what just sold'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "How many to return (max 20). Default 5.", "default": 5},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "old_transactions",
            "description": (
                "Summary of transactions older than N days (default 7). "
                "Use for questions about stale transactions, old orders, historical volume, "
                "transactions before a certain point."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "older_than_days": {"type": "integer", "description": "Cutoff in days. Default 7.", "default": 7},
                },
                "required": [],
            },
        },
    },
]


TOOLS: dict[str, ToolFn] = {
    "product_sales_summary": product_sales_summary,
    "day_by_day_revenue_summary": day_by_day_revenue_summary,
    "staff_performance": staff_performance,
    "low_stock_items": low_stock_items,
    "forecast_reorder": forecast_reorder,
    "detection_source_mix": detection_source_mix,
    "recent_transactions": recent_transactions,
    "old_transactions": old_transactions,
}


async def dispatch(name: str, args: dict, session: AsyncSession) -> Any:
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    safe_args = args if isinstance(args, dict) else {}
    try:
        return await fn(session, **safe_args)
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
