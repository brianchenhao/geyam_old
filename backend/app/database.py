"""Async SQLAlchemy engine + tenant-scope event hook.

The hook auto-appends `tenant_id = :ctx` to every ORM SELECT on a tenant-scoped
table (any model with a `tenant_id` column). This is Phase 2's safety net — if
a router forgets to filter, the hook still stops cross-tenant data leaks.

Tables with `__tenant_root__ = True` (currently only Tenant) are exempt.
Bypass is allowed only when `tenant_context.set_scope_bypass(True)` is active
(used by the CLI and admin endpoints).
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, with_loader_criteria
from sqlalchemy import event, orm

from app.config import DATABASE_URL
from app import tenant_context

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    # Alembic owns schema (see Dockerfile CMD). This is a no-op kept for compatibility.
    return


def _install_tenant_scope_hook():
    """Register a do_orm_execute listener that appends a tenant_id filter to every
    ORM query targeting a model with a `tenant_id` column."""

    @event.listens_for(orm.Session, "do_orm_execute")
    def _filter_by_tenant(execute_state):
        if execute_state.is_select and not execute_state.is_column_load and not execute_state.is_relationship_load:
            if tenant_context.is_scope_bypassed():
                return
            tenant_id = tenant_context.get_current_tenant_id()
            if tenant_id is None:
                # No tenant set → do nothing (the router-level dep should have raised 401
                # already; if we filtered to NULL here we'd mask bugs by returning empty).
                return
            # Add a WHERE clause to every mapped class that has tenant_id but is not a root.
            for mapper in list(_iter_mapped_classes()):
                cls = mapper.class_
                if getattr(cls, "__tenant_root__", False):
                    continue
                if "tenant_id" in mapper.columns.keys():
                    execute_state.statement = execute_state.statement.options(
                        with_loader_criteria(cls, cls.tenant_id == tenant_id, include_aliases=True)
                    )


def _iter_mapped_classes():
    from app import models  # noqa: F401 — ensure registrations exist
    return list(Base.registry.mappers)


_install_tenant_scope_hook()
