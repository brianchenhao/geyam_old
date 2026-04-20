"""Mint a dev JWT for a given tenant handle. Owner OR cashier.
DO NOT use in production — skips Google OAuth. Local smoke testing only."""
import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Tenant, User  # noqa: E402
from app.security import create_token  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--handle", required=True)
    ap.add_argument("--role", choices=["owner", "cashier"], default="owner")
    args = ap.parse_args()

    async with SessionLocal() as s:
        tenant = await s.scalar(select(Tenant).where(Tenant.handle == args.handle))
        if tenant is None:
            print(f"! no tenant with handle={args.handle}")
            return
        user = await s.scalar(
            select(User)
            .where(User.tenant_id == tenant.id, User.role == args.role)
            .execution_options(skip_tenant_filter=True)
        )
        if user is None:
            print(f"! no {args.role} for tenant {args.handle}")
            return
        token = create_token(
            user_id=user.id, tenant_id=tenant.id, role=user.role, email=user.email
        )
        print(token)


if __name__ == "__main__":
    asyncio.run(main())
