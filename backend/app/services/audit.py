from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def write(
    session: AsyncSession,
    *,
    tenant_id: int,
    action: str,
    user_id: int | None = None,
    entity: str | None = None,
    entity_id: int | None = None,
    meta: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            meta=meta,
        )
    )
