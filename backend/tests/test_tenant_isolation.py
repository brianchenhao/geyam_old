"""Phase 2 gate: Tenant A session must NEVER see Tenant B's rows.

Run from the backend container:
    docker compose exec backend pytest -xvs tests/test_tenant_isolation.py
Or locally against the docker db:
    ALEMBIC_DATABASE_URL=... DATABASE_URL=postgresql+asyncpg://... pytest tests/test_tenant_isolation.py
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy import delete, select  # noqa: E402

from app import tenant_context  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.deps import bypass_tenant_scope  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_tenant_isolation():
    # --- SETUP: wipe any test rows and create 2 tenants each with 1 user ---
    async with SessionLocal() as s:
        async with bypass_tenant_scope():
            await s.execute(delete(User).where(User.username.in_(["isoA_owner", "isoB_owner"])))
            await s.execute(delete(Tenant).where(Tenant.handle.in_(["isoA", "isoB"])))
            await s.commit()

            tA = Tenant(handle="isoA", name="Tenant A", owner_email="ownerA@iso.test")
            tB = Tenant(handle="isoB", name="Tenant B", owner_email="ownerB@iso.test")
            s.add_all([tA, tB]); await s.flush()
            s.add_all([
                User(tenant_id=tA.id, username="isoA_owner", email="ownerA@iso.test", role="owner"),
                User(tenant_id=tB.id, username="isoB_owner", email="ownerB@iso.test", role="owner"),
            ])
            await s.commit()
            tA_id, tB_id = tA.id, tB.id

    # --- A session scoped to tenant A sees ONLY A ---
    tenant_context.set_current_tenant_id(tA_id)
    async with SessionLocal() as s:
        rows = (await s.execute(select(User))).scalars().all()
        usernames = sorted(u.username for u in rows if u.username.startswith("iso"))
        assert usernames == ["isoA_owner"], f"tenant A saw cross-tenant rows: {usernames}"

    # --- A session scoped to tenant B sees ONLY B ---
    tenant_context.set_current_tenant_id(tB_id)
    async with SessionLocal() as s:
        rows = (await s.execute(select(User))).scalars().all()
        usernames = sorted(u.username for u in rows if u.username.startswith("iso"))
        assert usernames == ["isoB_owner"], f"tenant B saw cross-tenant rows: {usernames}"

    # --- bypass scope sees both (used by admin / CLI) ---
    tenant_context.set_current_tenant_id(None)
    async with SessionLocal() as s:
        async with bypass_tenant_scope():
            rows = (await s.execute(select(User))).scalars().all()
            usernames = sorted(u.username for u in rows if u.username.startswith("iso"))
            assert usernames == ["isoA_owner", "isoB_owner"], f"bypass missed rows: {usernames}"

    # --- No tenant set + no bypass → hook is a no-op (returns everything).
    # This is by design: we don't want to silently mask bugs by returning empty.
    # Router-level get_tenant() dep is what enforces 401 at the boundary.

    # Cleanup
    tenant_context.set_current_tenant_id(None)
    async with SessionLocal() as s:
        async with bypass_tenant_scope():
            await s.execute(delete(User).where(User.username.in_(["isoA_owner", "isoB_owner"])))
            await s.execute(delete(Tenant).where(Tenant.handle.in_(["isoA", "isoB"])))
            await s.commit()
