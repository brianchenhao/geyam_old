"""Async SQLAlchemy engine. Schema is owned by Alembic — do NOT call create_all."""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    # Alembic migrations run on container startup (see Dockerfile CMD).
    # This function is kept for API compatibility; it intentionally does nothing.
    return
