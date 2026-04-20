"""Alembic env. Uses sync psycopg driver because alembic doesn't run under asyncio here."""
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Prefer ALEMBIC_DATABASE_URL (sync driver); fall back to transforming DATABASE_URL.
_url = os.getenv("ALEMBIC_DATABASE_URL")
if not _url:
    _url = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg", "postgresql+psycopg")
if _url:
    config.set_main_option("sqlalchemy.url", _url)

target_metadata = None  # Raw SQL migrations; no SQLAlchemy autogenerate for now.


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
