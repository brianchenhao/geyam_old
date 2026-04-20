from contextvars import ContextVar

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, ORMExecuteState, Session, with_loader_criteria

from app.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


# Tables whose rows are scoped to a tenant — the event hook below transparently
# injects `tenant_id = <current_tenant>` into every SELECT against them.
# `tenants` itself is excluded (admins query it cross-tenant).
TENANT_SCOPED_MODELS: list[type] = []

current_tenant_id: ContextVar[int | None] = ContextVar("current_tenant_id", default=None)


def register_tenant_scoped(*models: type) -> None:
    for m in models:
        if m not in TENANT_SCOPED_MODELS:
            TENANT_SCOPED_MODELS.append(m)


@event.listens_for(Session, "do_orm_execute")
def _tenant_filter(state: ORMExecuteState) -> None:
    if not state.is_select:
        return
    if current_tenant_id.get() is None:
        return
    if state.execution_options.get("skip_tenant_filter"):
        return
    tid = current_tenant_id.get()
    for model in TENANT_SCOPED_MODELS:
        state.statement = state.statement.options(
            with_loader_criteria(
                model,
                model.tenant_id == tid,
                include_aliases=True,
            )
        )


async def init_db() -> None:
    from app import models  # noqa: F401  — register tables with Base.metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
