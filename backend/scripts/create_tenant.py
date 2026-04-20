"""CLI: create a new tenant + pre-create the owner user row.

Usage (inside the backend container):
    python scripts/create_tenant.py --email owner@example.com --handle myshop --name "My Shop"
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Allow running as a plain script from the repo layout
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.deps import bypass_tenant_scope  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402


async def run(email: str, handle: str, name: str) -> int:
    async with SessionLocal() as session:
        async with bypass_tenant_scope():
            existing = (await session.execute(
                select(Tenant).where((Tenant.handle == handle) | (Tenant.owner_email == email))
            )).scalars().first()
            if existing:
                print(f"ERROR: handle {handle!r} or email {email!r} already in tenants table", file=sys.stderr)
                return 2
            tenant = Tenant(handle=handle, name=name, owner_email=email)
            session.add(tenant)
            await session.flush()
            session.add(User(tenant_id=tenant.id, username=handle, email=email, role="owner"))
            await session.commit()
            print(f"OK: created tenant id={tenant.id} handle={handle!r} owner={email!r}")
            return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--handle", required=True)
    ap.add_argument("--name", required=True)
    args = ap.parse_args()
    rc = asyncio.run(run(args.email, args.handle, args.name))
    sys.exit(rc)


if __name__ == "__main__":
    main()
