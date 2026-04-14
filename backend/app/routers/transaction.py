from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models.menu_item import MenuItem
from app.models.transaction import Transaction, TransactionItem
from app.schemas.transaction import (
    SalesSummary,
    TopItem,
    TransactionCreate,
    TransactionCreated,
    TransactionOut,
)

router = APIRouter(tags=["sales"])


def _date_conditions(start_date: date | None, end_date: date | None) -> list:
    conds = []
    if start_date is not None:
        conds.append(
            Transaction.created_at
            >= datetime.combine(start_date, datetime.min.time())
        )
    if end_date is not None:
        conds.append(
            Transaction.created_at
            < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        )
    return conds


@router.post("/transaction", response_model=TransactionCreated)
async def create_transaction(payload: TransactionCreate):
    menu_item_ids = {i.menu_item_id for i in payload.items}

    async with SessionLocal() as session:
        existing_rows = await session.scalars(
            select(MenuItem.id).where(MenuItem.id.in_(menu_item_ids))
        )
        existing = set(existing_rows.all())
        missing = menu_item_ids - existing
        if missing:
            raise HTTPException(
                400, f"unknown menu_item_ids: {sorted(missing)}"
            )

        total = sum(
            (Decimal(str(i.unit_price)) * i.quantity for i in payload.items),
            Decimal("0"),
        )

        t = Transaction(
            staff_id=payload.staff_id,
            total=total,
            payment=payload.payment,
        )
        for i in payload.items:
            t.items.append(
                TransactionItem(
                    menu_item_id=i.menu_item_id,
                    quantity=i.quantity,
                    unit_price=Decimal(str(i.unit_price)),
                    confidence=i.confidence,
                )
            )
        session.add(t)
        await session.commit()
        await session.refresh(t)
        return TransactionCreated(
            id=t.id, total=float(t.total), created_at=t.created_at
        )


@router.get("/sales", response_model=list[TransactionOut])
async def list_sales(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
):
    conds = _date_conditions(start_date, end_date)
    async with SessionLocal() as session:
        stmt = (
            select(Transaction)
            .options(selectinload(Transaction.items))
            .order_by(desc(Transaction.created_at))
            .limit(limit)
        )
        if conds:
            stmt = stmt.where(and_(*conds))
        result = await session.scalars(stmt)
        return result.all()


@router.get("/sales/summary", response_model=SalesSummary)
async def sales_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    conds = _date_conditions(start_date, end_date)
    async with SessionLocal() as session:
        tx_stmt = select(
            func.coalesce(func.sum(Transaction.total), 0),
            func.count(Transaction.id),
        )
        if conds:
            tx_stmt = tx_stmt.where(and_(*conds))
        total_revenue, total_transactions = (
            await session.execute(tx_stmt)
        ).one()

        top_stmt = (
            select(
                MenuItem.id,
                MenuItem.name,
                func.sum(TransactionItem.quantity).label("qty"),
                func.sum(
                    TransactionItem.quantity * TransactionItem.unit_price
                ).label("rev"),
            )
            .join(Transaction, TransactionItem.transaction_id == Transaction.id)
            .join(MenuItem, TransactionItem.menu_item_id == MenuItem.id)
            .group_by(MenuItem.id, MenuItem.name)
            .order_by(desc("rev"))
            .limit(5)
        )
        if conds:
            top_stmt = top_stmt.where(and_(*conds))
        top_rows = (await session.execute(top_stmt)).all()

    return SalesSummary(
        total_revenue=float(total_revenue or 0),
        total_transactions=int(total_transactions or 0),
        top_selling_items=[
            TopItem(
                menu_item_id=r[0],
                name=r[1],
                quantity=int(r[2] or 0),
                revenue=float(r[3] or 0),
            )
            for r in top_rows
        ],
    )
