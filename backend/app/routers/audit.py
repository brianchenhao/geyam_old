"""Phase 12 — paginated audit feed for owner dashboard."""
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, get_tenant, require_role
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditOut(BaseModel):
    id: int
    user_id: Optional[int] = None
    action: str
    entity: Optional[str] = None
    entity_id: Optional[int] = None
    meta: Optional[dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", dependencies=[Depends(require_role("owner"))])
async def list_audit(
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    action_prefix: Optional[str] = None,
    tenant_id: int = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> list[AuditOut]:
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
    if action_prefix:
        stmt = stmt.where(AuditLog.action.like(f"{action_prefix}%"))
    rows = (await session.execute(stmt)).scalars().all()
    return [AuditOut.model_validate(r) for r in rows]
