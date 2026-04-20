"""Phase 2 gate: a session scoped to Tenant A MUST NOT see Tenant B rows."""
import asyncio
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.database import Base, current_tenant_id  # noqa: E402
from app.models import Tenant, User  # noqa: E402


@pytest.mark.asyncio
async def test_tenant_isolation():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with Session() as s:
        a = Tenant(handle="a", name="A", owner_email="a@x.com")
        b = Tenant(handle="b", name="B", owner_email="b@x.com")
        s.add_all([a, b])
        await s.flush()
        s.add_all([
            User(tenant_id=a.id, username="ua", role="owner", email="a@x.com"),
            User(tenant_id=b.id, username="ub", role="owner", email="b@x.com"),
        ])
        await s.commit()
        a_id, b_id = a.id, b.id

    async with Session() as s:
        tok = current_tenant_id.set(a_id)
        try:
            users = (await s.scalars(select(User))).all()
            assert [u.username for u in users] == ["ua"], f"leak: {users}"
        finally:
            current_tenant_id.reset(tok)

    async with Session() as s:
        tok = current_tenant_id.set(b_id)
        try:
            users = (await s.scalars(select(User))).all()
            assert [u.username for u in users] == ["ub"]
        finally:
            current_tenant_id.reset(tok)

    async with Session() as s:
        both = (
            await s.scalars(select(User).execution_options(skip_tenant_filter=True))
        ).all()
        assert {u.username for u in both} == {"ua", "ub"}


if __name__ == "__main__":
    asyncio.run(test_tenant_isolation())
    print("PASS")
