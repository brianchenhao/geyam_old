"""Deep health check for monitoring / load-balancer probes.

`/healthz` returns 200 only when DB, Redis, and disk space are all healthy.
On any failure it returns 503 with a JSON body naming the failing check, so
Healthchecks.io / UptimeRobot alerts carry enough context to triage without
opening the VPS.

`/health` (in main.py) is kept as a cheap liveness probe — it answers as soon
as uvicorn is up, even if DB/Redis aren't reachable.
"""
from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any

import redis.asyncio as async_redis
from fastapi import APIRouter, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import REDIS_URL
from app.database import SessionLocal

router = APIRouter(tags=["health"])

CHECK_TIMEOUT_S = 2.0
DISK_PATH = os.getenv("HEALTHZ_DISK_PATH", "/")
DISK_MIN_FREE_PCT = float(os.getenv("HEALTHZ_DISK_MIN_FREE_PCT", "10"))


async def _check_db() -> dict[str, Any]:
    try:
        async def _q() -> None:
            session: AsyncSession
            async with SessionLocal() as session:
                await session.execute(text("SELECT 1"))
        await asyncio.wait_for(_q(), timeout=CHECK_TIMEOUT_S)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def _check_redis() -> dict[str, Any]:
    client = async_redis.from_url(REDIS_URL)
    try:
        pong = await asyncio.wait_for(client.ping(), timeout=CHECK_TIMEOUT_S)
        return {"ok": bool(pong)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        try:
            await client.aclose()
        except Exception:
            pass


def _check_disk() -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(DISK_PATH)
        free_pct = (usage.free / usage.total) * 100
        return {
            "ok": free_pct >= DISK_MIN_FREE_PCT,
            "path": DISK_PATH,
            "free_pct": round(free_pct, 1),
            "threshold_pct": DISK_MIN_FREE_PCT,
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@router.api_route("/healthz", methods=["GET", "HEAD"])
async def healthz(response: Response) -> dict[str, Any]:
    db_result, redis_result = await asyncio.gather(_check_db(), _check_redis())
    disk_result = _check_disk()
    checks = {"db": db_result, "redis": redis_result, "disk": disk_result}
    healthy = all(c.get("ok") for c in checks.values())
    response.status_code = 200 if healthy else 503
    return {"status": "ok" if healthy else "degraded", "checks": checks}
