"""Auto-void stale pending transactions. Runs every 60s.

A tx is stale if status='pending' and created_at < now - 10 minutes.
Void sets voided_by=NULL to mark a system auto-void.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, current_tenant_id  # noqa: E402
from app.models import Transaction  # noqa: E402
from app.services import audit, ws_hub  # noqa: E402

logging.basicConfig(level=logging.INFO, format="[autovoid] %(asctime)s %(message)s")
HEARTBEAT_SEC = int(os.getenv("AUTOVOID_INTERVAL_SEC", "60"))
STALE_MINUTES = int(os.getenv("AUTOVOID_STALE_MINUTES", "10"))


async def sweep_once() -> int:
    cutoff = datetime.utcnow() - timedelta(minutes=STALE_MINUTES)
    async with SessionLocal() as s:
        stale = (await s.scalars(
            select(Transaction)
            .where(Transaction.status == "pending",
                   Transaction.created_at < cutoff)
            .execution_options(skip_tenant_filter=True)
        )).all()
        for tx in stale:
            tok = current_tenant_id.set(tx.tenant_id)
            try:
                tx.status = "voided"
                tx.voided_at = datetime.utcnow()
                tx.voided_by = None
                await audit.write(
                    s, tenant_id=tx.tenant_id,
                    action="tx.auto_void", entity="transaction", entity_id=tx.id,
                    meta={"tx_number": tx.tx_number,
                          "age_sec": int(
                              (datetime.utcnow() - tx.created_at).total_seconds()
                          )},
                )
                await ws_hub.broadcast(tx.tenant_id, "tx_autovoid", {
                    "tx_id": tx.id, "tx_number": tx.tx_number,
                })
            finally:
                current_tenant_id.reset(tok)
        if stale:
            await s.commit()
        return len(stale)


async def main() -> None:
    logging.info("autovoid loop starting; interval=%ds, stale=%dm",
                 HEARTBEAT_SEC, STALE_MINUTES)
    while True:
        try:
            n = await sweep_once()
            if n:
                logging.info("auto-voided %d stale transactions", n)
            else:
                logging.info("heartbeat")
        except Exception as e:
            logging.exception("sweep error: %s", e)
        await asyncio.sleep(HEARTBEAT_SEC)


if __name__ == "__main__":
    asyncio.run(main())
