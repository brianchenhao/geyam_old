"""Phase 11 — public Antsilk attack counter for the geyam.com landing page.

Unauthenticated, intentionally minimal: a single number ("X attacks blocked
since launch") + a small per-rule breakdown. No IP, no user-agent, no
timestamps below the day level — anything that could identify a request is
omitted. This is marketing/SEO data, not an admin tool. The admin-gated
counterpart lives at /admin/antsilk/stats (Phase 7).

CORS is already configured app-wide to allow geyam.com, so a JS/Flutter web
client served from there can hit this directly.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import bypass_tenant_scope, get_session

router = APIRouter(prefix="/antsilk", tags=["antsilk"])


@router.get("/stats/public")
async def public_stats(session: AsyncSession = Depends(get_session)) -> dict:
    """Return all-time blocked-request totals and a per-rule breakdown.

    Numbers only — no IP, UA, timestamps, paths. Cached at the CDN edge for
    60s is a reasonable add later (Caddy directive, not implemented here).
    """
    async with bypass_tenant_scope():
        total = (await session.execute(
            text("SELECT count(*) FROM antsilk_events")
        )).scalar_one()
        by_rule = (await session.execute(
            text(
                "SELECT rule_triggered, count(*) AS c FROM antsilk_events "
                "GROUP BY rule_triggered ORDER BY c DESC"
            )
        )).all()
    return {
        "total_blocked": int(total),
        "by_rule": {r: int(c) for r, c in by_rule},
    }
