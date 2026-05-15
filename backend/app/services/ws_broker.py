"""Redis pub/sub bridge between out-of-process workers and the in-process ws hub.

The FastAPI container owns the WebSocket connections (app.websocket.hub). Other
processes — the autovoid scheduler, the RQ worker — can't reach that hub
directly, so they publish JSON messages to a Redis channel which the FastAPI
process subscribes to on startup and forwards to the hub.
"""
import asyncio
import json
import os
from typing import Any

import redis as sync_redis
import redis.asyncio as async_redis

from app.config import REDIS_URL


CHANNEL = "geyam:ws"


def publish_sync(tenant_id: int, message: dict[str, Any]) -> None:
    """Fire-and-forget publish from a sync context (worker/scheduler)."""
    try:
        client = sync_redis.Redis.from_url(REDIS_URL)
        payload = json.dumps({"tenant_id": int(tenant_id), "message": message})
        client.publish(CHANNEL, payload)
    except Exception as e:
        print(f"[ws_broker] publish_sync failed: {type(e).__name__}: {e}", flush=True)


async def run_subscriber(hub) -> None:
    """Long-lived task: forward Redis pub/sub messages to the in-process hub."""
    client = async_redis.from_url(REDIS_URL)
    pubsub = client.pubsub()
    await pubsub.subscribe(CHANNEL)
    try:
        async for raw in pubsub.listen():
            if raw is None or raw.get("type") != "message":
                continue
            try:
                data = json.loads(raw["data"])
                tenant_id = int(data["tenant_id"])
                await hub.publish(tenant_id, data["message"])
            except Exception as e:
                print(f"[ws_broker] forward error: {type(e).__name__}: {e}", flush=True)
    except asyncio.CancelledError:
        pass
    finally:
        try:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.close()
            await client.close()
        except Exception:
            pass
