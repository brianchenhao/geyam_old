"""Phase 9 step 9 — flip past_due subscriptions to suspended after 7 days.

Runs as a daily cron. Idempotent: subscriptions already suspended are skipped.

Logic:
  - For every subscription with status='past_due' and past_due_since > 7d ago:
      - subscription.status = 'suspended'
      - subscription.suspended_at = now()
      - tenant.status = 'suspended' (mirror — read-hot, used by quota gate)
      - Write admin_audit_log row with actor='system.sweeper' for the trail.

Invoke:
  docker exec geyam-backend-1 python -m scripts.sweep_past_due
or via cron:
  0 4 * * * docker exec geyam-backend-1 python -m scripts.sweep_past_due

Exit code: 0 always (a sweep that flips zero rows is success). Errors go to
stderr and the admin audit row (success=false) for traceability.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make `from app.*` importable when invoked via `python -m scripts.sweep_past_due`
# from outside the backend/ dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.deps import bypass_tenant_scope  # noqa: E402
from app.models.subscription import Subscription  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.services.audit import write_audit_event  # noqa: E402

GRACE_PERIOD_DAYS = 7

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sweep_past_due")


async def sweep() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=GRACE_PERIOD_DAYS)
    flipped = 0
    async with SessionLocal() as session:
        async with bypass_tenant_scope():
            stale = (await session.execute(
                select(Subscription).where(
                    Subscription.status == "past_due",
                    Subscription.past_due_since != None,  # noqa: E711
                    Subscription.past_due_since < cutoff,
                )
            )).scalars().all()
            log.info("found %d past_due subscriptions older than %dd", len(stale), GRACE_PERIOD_DAYS)
            now = datetime.now(timezone.utc)
            for sub in stale:
                before = {"status": sub.status, "past_due_since": sub.past_due_since.isoformat()}
                sub.status = "suspended"
                sub.suspended_at = now
                tenant = (await session.execute(
                    select(Tenant).where(Tenant.id == sub.tenant_id)
                )).scalars().first()
                if tenant is not None:
                    tenant.status = "suspended"
                await write_audit_event(
                    session,
                    actor_email="system.sweeper",
                    action="subscription.auto_suspend",
                    tenant_id=sub.tenant_id,
                    before_data=before,
                    after_data={"status": "suspended", "suspended_at": now.isoformat()},
                    success=True,
                )
                flipped += 1
                log.info("suspended tenant_id=%d (past_due since %s)",
                         sub.tenant_id, sub.past_due_since.isoformat())
            await session.commit()
    return flipped


def main() -> int:
    try:
        flipped = asyncio.run(sweep())
        log.info("sweep done; %d subscription(s) suspended", flipped)
        return 0
    except Exception:
        log.exception("sweep_past_due failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
