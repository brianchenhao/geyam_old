"""Generate GY{YYYYMMDD}-{NNNN} transaction numbers serialized per-tenant per-day."""
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def next_tx_number(session: AsyncSession, tenant_id: int) -> str:
    today = date.today().strftime("%Y%m%d")
    # Count today's rows for this tenant with FOR UPDATE semantics on the count row.
    # Since Postgres can't lock "a count", we lock the tenants row to serialize concurrent creators.
    await session.execute(text("SELECT id FROM tenants WHERE id=:t FOR UPDATE"), {"t": tenant_id})
    row = await session.execute(
        text("SELECT COUNT(*) FROM transactions WHERE tenant_id=:t AND tx_number LIKE :p"),
        {"t": tenant_id, "p": f"GY{today}-%"},
    )
    count = row.scalar() or 0
    return f"GY{today}-{count + 1:04d}"
