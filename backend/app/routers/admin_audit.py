"""GET /admin/audit-log — paginate + filter the admin_audit_log table.
GET /admin/audit-log/{id} — fetch one row.

Restricted to ADMIN_EMAILS (require_admin). NOT tenant-scoped — admins read
across all tenants by design (that's the entire point of an admin trail).
"""
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import bypass_tenant_scope, get_session, require_admin
from app.models.admin_audit_log import AdminAuditLog

router = APIRouter(prefix="/admin/audit-log", tags=["admin-audit"])


class AdminAuditOut(BaseModel):
    id: int
    ts: datetime
    actor_email: str
    actor_ip: Optional[str] = None
    tenant_id: Optional[int] = None
    action: str
    before_data: Optional[dict[str, Any]] = None
    after_data: Optional[dict[str, Any]] = None
    request_id: Optional[str] = None
    success: bool

    model_config = {"from_attributes": True}


@router.get("", dependencies=[Depends(require_admin)])
async def list_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action_prefix: Optional[str] = None,
    actor_email: Optional[str] = None,
    tenant_id: Optional[int] = None,
    success: Optional[bool] = None,
    session: AsyncSession = Depends(get_session),
) -> list[AdminAuditOut]:
    async with bypass_tenant_scope():
        stmt = select(AdminAuditLog).order_by(AdminAuditLog.id.desc())
        if action_prefix:
            stmt = stmt.where(AdminAuditLog.action.like(f"{action_prefix}%"))
        if actor_email:
            stmt = stmt.where(AdminAuditLog.actor_email == actor_email)
        if tenant_id is not None:
            stmt = stmt.where(AdminAuditLog.tenant_id == tenant_id)
        if success is not None:
            stmt = stmt.where(AdminAuditLog.success == success)
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = (await session.execute(stmt)).scalars().all()
    return [AdminAuditOut.model_validate(r) for r in rows]


@router.get("/{audit_id}", dependencies=[Depends(require_admin)])
async def get_audit(
    audit_id: int,
    session: AsyncSession = Depends(get_session),
) -> AdminAuditOut:
    async with bypass_tenant_scope():
        row = (await session.execute(
            select(AdminAuditLog).where(AdminAuditLog.id == audit_id)
        )).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="audit row not found")
    return AdminAuditOut.model_validate(row)
