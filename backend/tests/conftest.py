"""Test-scoped overrides.

Use a NullPool async engine so every session gets a fresh asyncpg connection.
Without this, connections stay bound to the event loop from the first test that
used them, and later tests on a new loop get 'another operation in progress' or
'attached to a different loop' errors.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import database
from app.config import DATABASE_URL

_test_engine = create_async_engine(DATABASE_URL, echo=False, poolclass=NullPool)
_test_sessionmaker = async_sessionmaker(_test_engine, expire_on_commit=False, class_=AsyncSession)

database.engine = _test_engine
database.SessionLocal = _test_sessionmaker
