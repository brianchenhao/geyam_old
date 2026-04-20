"""Auto-void scheduler. Phase 1: boots + logs heartbeat every 60s.
Phase 8 wires the real stale-pending-transaction void loop."""
import logging
import time

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="[autovoid] %(asctime)s %(message)s")
HEARTBEAT_SEC = 60

if __name__ == "__main__":
    logging.info("autovoid scheduler starting; heartbeat every %ds", HEARTBEAT_SEC)
    while True:
        logging.info("heartbeat")
        time.sleep(HEARTBEAT_SEC)
