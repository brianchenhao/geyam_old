"""Atomic tx_number generator — GY{YYYYMMDD}-{N}.

Serialised per (tenant_id, day) via pg_advisory_xact_lock so two concurrent
POST /transaction calls cannot mint the same number. The lock lives for the
duration of the enclosing transaction; once committed, the count for (tenant,
today) is locked in and the next caller gets N+1.
"""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Transaction


async def next_number(session: AsyncSession, *, tenant_id: int) -> str:
    today = date.today()
    prefix = f"GY{today.strftime('%Y%m%d')}-"

    # Advisory lock keyed to (tenant_id, yyyymmdd) so only one open session per
    # tenant+day proceeds at a time. Postgres only — on SQLite we skip and rely
    # on the UNIQUE constraint to surface a collision (tests use retry).
    if session.bind.dialect.name == "postgresql":
        key = (tenant_id * 100000000) + int(today.strftime("%Y%m%d"))
        await session.execute(func.pg_advisory_xact_lock(key))

    count = await session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.tenant_id == tenant_id,
               Transaction.tx_number.like(f"{prefix}%"))
        .execution_options(skip_tenant_filter=True)
    )
    return f"{prefix}{(count or 0) + 1:04d}"
