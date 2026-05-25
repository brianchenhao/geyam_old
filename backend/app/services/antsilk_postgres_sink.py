"""Custom antsilk.EventSink that writes WAF events to the main Geyam DB.

The antsilk middleware calls ``write()`` via ``asyncio.to_thread``, so this
sink runs in a worker thread and must use a sync driver. psycopg 3 (already
in requirements) fits; asyncpg would force an asyncio.run() bridge.

Per PLAN-stage3-Geyam.md "Anti-Mistake Habits": sink failures must NEVER
propagate. A broken WAF logger should not turn into a 500 for legitimate
traffic. We log to stderr and return None on any error. The antsilk
middleware catches too — this is defence in depth.

tenant_id is always NULL because the antsilk middleware runs OUTSIDE the
auth/tenant-context stack (that's the point — block hostile traffic before
any per-request work). Future enhancement: backfill from path inference,
e.g. /admin/tenants/{id}/... → tenant_id, if useful.
"""
from __future__ import annotations

import json
import logging

import psycopg

from antsilk import Event, EventSink

from app.config import DATABASE_URL

_LOG = logging.getLogger("geyam.antsilk_postgres_sink")


def _sync_dsn(asyncpg_url: str) -> str:
    """Convert SQLAlchemy's asyncpg URL to a plain psycopg DSN."""
    return asyncpg_url.replace("postgresql+asyncpg://", "postgresql://", 1)


class AntsilkPostgresSink(EventSink):
    """Writes each Event as one row into the antsilk_events table.

    Opens a short-lived connection per write — matches SQLiteSink's pattern
    and avoids holding a pool open in a sink that fires only on blocked
    requests (a few/sec at peak, not request-rate).
    """

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn or _sync_dsn(DATABASE_URL)

    def write(self, event: Event) -> None:
        # antsilk's own Event.app_id has no column in our schema; fold it
        # into event_data so we don't lose it if a future config sets it.
        payload = dict(event.event_data)
        if event.app_id is not None:
            payload.setdefault("app_id", event.app_id)

        try:
            with psycopg.connect(self._dsn, autocommit=True) as conn:
                conn.execute(
                    "INSERT INTO antsilk_events"
                    " (timestamp, ip_address, method, path, rule_triggered,"
                    "  severity, response_code, user_agent, event_data)"
                    " VALUES (%s, %s::inet, %s, %s, %s, %s, %s, %s, %s::jsonb)",
                    (
                        event.timestamp,
                        event.ip_address,
                        event.method,
                        event.path,
                        event.rule_triggered,
                        event.severity,
                        event.response_code,
                        event.user_agent,
                        json.dumps(payload),
                    ),
                )
        except Exception:
            _LOG.exception(
                "AntsilkPostgresSink write failed (rule=%s ip=%s)",
                event.rule_triggered,
                event.ip_address,
            )
