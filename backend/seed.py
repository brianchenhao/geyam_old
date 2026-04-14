"""Seed initial users: one staff, one manager. Safe to re-run."""
import asyncio

import bcrypt
from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models.user import User

SEED_USERS = [
    {"username": "staff1", "password": "staff123", "role": "staff"},
    {"username": "manager1", "password": "manager123", "role": "manager"},
]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def main() -> None:
    await init_db()
    async with SessionLocal() as session:
        for u in SEED_USERS:
            existing = await session.scalar(
                select(User).where(User.username == u["username"])
            )
            if existing:
                print(f"skip {u['username']} (exists)")
                continue
            session.add(
                User(
                    username=u["username"],
                    password=hash_password(u["password"]),
                    role=u["role"],
                )
            )
            print(f"added {u['username']} ({u['role']})")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
