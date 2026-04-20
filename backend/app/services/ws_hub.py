"""In-memory WebSocket fan-out, per tenant.

The hub tracks {tenant_id → set[WebSocket]}. Any backend path that wants to push
an event calls `broadcast(tenant_id, event_type, payload)` and each connected
client in that tenant receives the same JSON message.

For a single-laptop backend this is fine. If we ever horizontal-scale, swap the
in-process dict for a Redis pubsub channel keyed by tenant_id.
"""
import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket

_lock = asyncio.Lock()
_connections: dict[int, set[WebSocket]] = defaultdict(set)


async def register(tenant_id: int, ws: WebSocket) -> None:
    async with _lock:
        _connections[tenant_id].add(ws)


async def unregister(tenant_id: int, ws: WebSocket) -> None:
    async with _lock:
        _connections[tenant_id].discard(ws)
        if not _connections[tenant_id]:
            _connections.pop(tenant_id, None)


async def broadcast(tenant_id: int, event_type: str, payload: dict | None = None) -> int:
    """Send {type, payload} to every socket for this tenant. Returns count sent."""
    msg = json.dumps({"type": event_type, "payload": payload or {}})
    dead: list[WebSocket] = []
    async with _lock:
        targets = list(_connections.get(tenant_id, ()))
    for ws in targets:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for d in dead:
        await unregister(tenant_id, d)
    return len(targets) - len(dead)


def _connections_snapshot() -> dict[int, int]:
    """Test helper: {tenant_id: connection_count}"""
    return {tid: len(s) for tid, s in _connections.items()}
