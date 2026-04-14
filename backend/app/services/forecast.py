"""Moving-average sales forecast.

Computes per-product sales stats over a fixed window (14 days by default),
split into two 7-day halves to derive a simple trend direction.
One aggregate SQL query does the heavy lifting; everything else is Python math.
"""
from datetime import datetime, timedelta

from sqlalchemy import case, func, select

from app.database import SessionLocal
from app.models.menu_item import MenuItem
from app.models.transaction import Transaction, TransactionItem

WINDOW_DAYS = 14
RECENT_DAYS = 7
MIN_UNITS_FOR_CONFIDENCE = 3


async def compute_forecast() -> list[dict]:
    end = datetime.now()
    start = end - timedelta(days=WINDOW_DAYS)
    mid = end - timedelta(days=RECENT_DAYS)

    async with SessionLocal() as session:
        items = (
            await session.scalars(
                select(MenuItem)
                .where(MenuItem.is_active.is_(True))
                .order_by(MenuItem.id)
            )
        ).all()

        agg_stmt = (
            select(
                TransactionItem.menu_item_id,
                func.sum(TransactionItem.quantity).label("total"),
                func.sum(
                    case(
                        (Transaction.created_at >= mid, TransactionItem.quantity),
                        else_=0,
                    )
                ).label("recent"),
                func.sum(
                    case(
                        (Transaction.created_at < mid, TransactionItem.quantity),
                        else_=0,
                    )
                ).label("prev"),
            )
            .join(Transaction, TransactionItem.transaction_id == Transaction.id)
            .where(Transaction.created_at >= start)
            .where(Transaction.created_at < end)
            .group_by(TransactionItem.menu_item_id)
        )
        rows = (await session.execute(agg_stmt)).all()

    by_id = {
        r.menu_item_id: (int(r.total or 0), int(r.recent or 0), int(r.prev or 0))
        for r in rows
    }

    out: list[dict] = []
    for mi in items:
        total, recent, prev = by_id.get(mi.id, (0, 0, 0))
        avg_daily = total / WINDOW_DAYS
        predicted = avg_daily * 7
        if recent > prev:
            trend = "up"
        elif recent < prev:
            trend = "down"
        else:
            trend = "flat"
        note = "insufficient data" if total < MIN_UNITS_FOR_CONFIDENCE else None
        out.append(
            {
                "menu_item_id": mi.id,
                "name": mi.name,
                "days_analyzed": WINDOW_DAYS,
                "total_sold": total,
                "avg_daily_sales": round(avg_daily, 2),
                "predicted_next_week": round(predicted, 1),
                "trend": trend,
                "note": note,
            }
        )
    return out
