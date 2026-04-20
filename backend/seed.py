"""Stage 2 dev seed: one tenant for the admin, one cashier under it."""
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(Path(__file__).resolve().parent / ".env")

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Tenant, TenantSettings, User  # noqa: E402
from app.security import hash_pin  # noqa: E402

ADMIN_EMAIL = "brianchen.crisp@gmail.com"
HANDLE = "brianchenjunhao"
SHOP_NAME = "Brian's Demo Shop"
CASHIER_PIN = "123456"


async def main() -> None:
    await init_db()
    async with SessionLocal() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.handle == HANDLE))
        if tenant is None:
            tenant = Tenant(handle=HANDLE, name=SHOP_NAME, owner_email=ADMIN_EMAIL)
            session.add(tenant)
            await session.flush()
            session.add(TenantSettings(tenant_id=tenant.id))
            session.add(
                User(
                    tenant_id=tenant.id,
                    username=f"owner.{HANDLE}",
                    email=ADMIN_EMAIL,
                    role="owner",
                )
            )
            print(f"+ tenant {tenant.handle} (owner={ADMIN_EMAIL})")
        else:
            print(f"= tenant {tenant.handle} already exists")

        cashier = await session.scalar(
            select(User)
            .where(User.tenant_id == tenant.id, User.username == f"staff1.{HANDLE}")
            .execution_options(skip_tenant_filter=True)
        )
        if cashier is None:
            session.add(
                User(
                    tenant_id=tenant.id,
                    username=f"staff1.{HANDLE}",
                    pin_hash=hash_pin(CASHIER_PIN),
                    role="cashier",
                )
            )
            print(f"+ cashier staff1.{HANDLE} (pin={CASHIER_PIN})")

        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
