"""Phase 7 — admin read endpoints over the antsilk_events WAF log.

Both endpoints are gated by ADMIN_EMAILS (require_admin). antsilk_events
has no ORM model — the table is owned by the Antsilk middleware sink, not
the application, and a one-shot read API doesn't justify a mapped class.
Raw SQL via text() keeps the surface narrow.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import bypass_tenant_scope, get_session, require_admin

router = APIRouter(prefix="/admin/antsilk", tags=["admin", "antsilk"])


class AntsilkEventOut(BaseModel):
    id: int
    timestamp: datetime
    tenant_id: Optional[int]
    ip_address: str
    method: str
    path: str
    rule_triggered: str
    severity: str
    response_code: int
    user_agent: Optional[str]
    event_data: dict[str, Any]


@router.get("/events", dependencies=[Depends(require_admin)])
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    rule: Optional[str] = Query(None, description="Exact rule_triggered match"),
    severity: Optional[str] = Query(None, pattern="^(low|medium|high)$"),
    since_hours: Optional[int] = Query(None, ge=1, le=24 * 30),
    session: AsyncSession = Depends(get_session),
) -> list[AntsilkEventOut]:
    """Paginated WAF event log. Newest first."""
    where: list[str] = []
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
    if rule:
        where.append("rule_triggered = :rule")
        params["rule"] = rule
    if severity:
        where.append("severity = :severity")
        params["severity"] = severity
    if since_hours:
        where.append("timestamp >= now() - (:hrs || ' hours')::interval")
        params["hrs"] = str(since_hours)

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    sql = text(
        "SELECT id, timestamp, tenant_id, host(ip_address) AS ip_address, method, path,"
        "       rule_triggered, severity, response_code, user_agent, event_data"
        "  FROM antsilk_events" + where_sql +
        " ORDER BY id DESC LIMIT :limit OFFSET :offset"
    )

    async with bypass_tenant_scope():
        result = await session.execute(sql, params)
        rows = result.mappings().all()

    return [AntsilkEventOut(**dict(r)) for r in rows]


class AntsilkStatsOut(BaseModel):
    window_hours: int
    total: int
    by_rule: dict[str, int]
    by_severity: dict[str, int]
    top_ips: list[dict[str, Any]]


@router.get("/stats", dependencies=[Depends(require_admin)])
async def stats(
    hours: int = Query(24, ge=1, le=24 * 30),
    session: AsyncSession = Depends(get_session),
) -> AntsilkStatsOut:
    """Aggregate counts over the last `hours` window. Defaults to 24h."""
    base_where = "WHERE timestamp >= now() - (:hrs || ' hours')::interval"
    params = {"hrs": str(hours)}

    async with bypass_tenant_scope():
        total = (await session.execute(
            text(f"SELECT count(*) FROM antsilk_events {base_where}"), params
        )).scalar_one()

        by_rule_rows = (await session.execute(
            text(
                f"SELECT rule_triggered, count(*) AS c FROM antsilk_events {base_where}"
                " GROUP BY rule_triggered ORDER BY c DESC"
            ),
            params,
        )).all()

        by_sev_rows = (await session.execute(
            text(
                f"SELECT severity, count(*) AS c FROM antsilk_events {base_where}"
                " GROUP BY severity ORDER BY c DESC"
            ),
            params,
        )).all()

        top_ip_rows = (await session.execute(
            text(
                f"SELECT host(ip_address) AS ip, count(*) AS c FROM antsilk_events {base_where}"
                " GROUP BY ip_address ORDER BY c DESC LIMIT 10"
            ),
            params,
        )).all()

    return AntsilkStatsOut(
        window_hours=hours,
        total=int(total or 0),
        by_rule={r[0]: int(r[1]) for r in by_rule_rows},
        by_severity={r[0]: int(r[1]) for r in by_sev_rows},
        top_ips=[{"ip": r[0], "count": int(r[1])} for r in top_ip_rows],
    )
