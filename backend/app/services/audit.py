"""One-line helper to insert an audit_logs row. Intentionally tolerant:
auth-fail rows can carry tenant_id=NULL and user_id=NULL.
"""
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def audit(
    session: AsyncSession,
    *,
    action: str,
    tenant_id: Optional[int] = None,
    user_id: Optional[int] = None,
    entity: Optional[str] = None,
    entity_id: Optional[int] = None,
    meta: Optional[dict[str, Any]] = None,
) -> None:
    session.add(AuditLog(
        action=action, tenant_id=tenant_id, user_id=user_id,
        entity=entity, entity_id=entity_id, meta=meta,
    ))
    # Caller is responsible for commit (usually batched with the mutation).
