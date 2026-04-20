"""Phase 12: paginated audit log viewer (owner only)."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import Principal, get_session, require_role
from app.models import AuditLog, User

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditOut(BaseModel):
    id: int
    created_at: datetime
    action: str
    entity: str | None
    entity_id: int | None
    user_id: int | None
    username: str | None
    meta: dict | None


class AuditPage(BaseModel):
    total: int
    limit: int
    offset: int
    rows: list[AuditOut]


@router.get("", response_model=AuditPage)
async def list_audit(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action: str | None = None,
    entity: str | None = None,
    p: Principal = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)

    total = await session.scalar(
        select(func.count(AuditLog.id)).where(
            *([AuditLog.action == action] if action else []),
            *([AuditLog.entity == entity] if entity else []),
        )
    ) or 0

    rows = (await session.scalars(stmt.offset(offset).limit(limit))).all()

    # usernames in one batch
    uids = {r.user_id for r in rows if r.user_id is not None}
    name_map: dict[int, str] = {}
    if uids:
        for u in (await session.scalars(
            select(User).where(User.id.in_(uids))
        )).all():
            name_map[u.id] = u.username

    return AuditPage(
        total=int(total), limit=limit, offset=offset,
        rows=[AuditOut(
            id=r.id, created_at=r.created_at, action=r.action,
            entity=r.entity, entity_id=r.entity_id,
            user_id=r.user_id, username=name_map.get(r.user_id) if r.user_id else None,
            meta=r.meta,
        ) for r in rows],
    )
