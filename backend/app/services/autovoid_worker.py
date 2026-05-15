"""Auto-void scheduler. Phase 8 active: marks pending TX older than 10 min as voided."""
import os
import time
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


HEARTBEAT_SECS = int(os.getenv("AUTOVOID_HEARTBEAT_SECS", "60"))
TIMEOUT_MINUTES = int(os.getenv("AUTOVOID_MINUTES", "10"))


def _sessionmaker():
    sync_url = os.environ.get("ALEMBIC_DATABASE_URL") or \
        os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql+psycopg")
    engine = create_engine(sync_url, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _tick(Maker):
    from app.models.audit_log import AuditLog
    from app.models.transaction import Transaction
    from app.services.ws_broker import publish_sync
    cutoff = datetime.utcnow() - timedelta(minutes=TIMEOUT_MINUTES)
    notify: list[tuple[int, int, str]] = []  # (tenant_id, tx_id, tx_number)
    with Maker() as s:
        stale = s.execute(
            select(Transaction).where(Transaction.status == "pending", Transaction.created_at < cutoff)
        ).scalars().all()
        for tx in stale:
            tx.status = "voided"
            tx.voided_at = datetime.utcnow()
            tx.voided_by = None  # system
            s.add(AuditLog(tenant_id=tx.tenant_id, user_id=None, action="tx.auto_void",
                           entity="transaction", entity_id=tx.id,
                           meta={"tx_number": tx.tx_number}))
            notify.append((tx.tenant_id, tx.id, tx.tx_number))
        if stale:
            print(f"[autovoid] voided {len(stale)} stale pending tx(s)", flush=True)
        s.commit()

    for tenant_id, tx_id, tx_number in notify:
        publish_sync(tenant_id, {
            "type": "tx_autovoid",
            "tx_id": tx_id,
            "tx_number": tx_number,
        })


def main() -> None:
    print(f"[autovoid] started; timeout={TIMEOUT_MINUTES}min heartbeat={HEARTBEAT_SECS}s", flush=True)
    Maker = None
    while True:
        try:
            if Maker is None:
                Maker = _sessionmaker()
            _tick(Maker)
        except Exception as e:
            print(f"[autovoid] tick error: {type(e).__name__}: {e}", flush=True)
            Maker = None  # rebuild on next loop
        time.sleep(HEARTBEAT_SECS)


if __name__ == "__main__":
    main()
