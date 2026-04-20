"""Create a tenant + its owner user row. Admin CLI, runs off-laptop.

Example:
    python scripts/create_tenant.py --email brian@example.com \
        --handle brianshop --name "Brian's Shop"
"""
import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Tenant, TenantSettings, User  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--handle", required=True)
    ap.add_argument("--name", required=True)
    args = ap.parse_args()

    async with SessionLocal() as session:
        exists = await session.scalar(select(Tenant).where(Tenant.handle == args.handle))
        if exists:
            print(f"! tenant handle '{args.handle}' already exists (id={exists.id})")
            return

        tenant = Tenant(
            handle=args.handle, name=args.name, owner_email=args.email.lower()
        )
        session.add(tenant)
        try:
            await session.flush()
        except IntegrityError as e:
            print(f"! failed to create tenant: {e.orig}")
            return
        session.add(TenantSettings(tenant_id=tenant.id))
        session.add(
            User(
                tenant_id=tenant.id,
                username=f"owner.{tenant.handle}",
                email=tenant.owner_email,
                role="owner",
            )
        )
        await session.commit()
        print(f"✓ tenant id={tenant.id} handle={tenant.handle} owner={tenant.owner_email}")


if __name__ == "__main__":
    asyncio.run(main())
