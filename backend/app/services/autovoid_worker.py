"""Auto-void scheduler. Phase 1 skeleton: heartbeat only.

Phase 8 will expand this to query pending transactions older than 10 minutes,
mark them voided, emit audit entries, and push WebSocket notifications.
"""
import os
import time

HEARTBEAT_SECS = int(os.getenv("AUTOVOID_HEARTBEAT_SECS", "60"))


def main() -> None:
    print("[autovoid] scheduler started; heartbeat every", HEARTBEAT_SECS, "s", flush=True)
    while True:
        print("[autovoid] heartbeat (phase 1 skeleton; no-op)", flush=True)
        time.sleep(HEARTBEAT_SECS)


if __name__ == "__main__":
    main()
