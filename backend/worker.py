"""RQ worker entry point. Phase 1: boots + logs heartbeat waiting for jobs.
Phase 6 wires real training jobs onto the 'training' queue."""
import logging
import os

from redis import Redis
from rq import Queue, Worker
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380/0")
QUEUES = ["training", "default"]

logging.basicConfig(level=logging.INFO, format="[worker] %(asctime)s %(message)s")

if __name__ == "__main__":
    conn = Redis.from_url(REDIS_URL)
    logging.info("waiting for jobs on queues: %s (redis=%s)", QUEUES, REDIS_URL)
    Worker([Queue(name, connection=conn) for name in QUEUES], connection=conn).work()
