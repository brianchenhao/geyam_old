"""Per-tenant WebSocket hub.

Topology: one hub object in process; each connection carries a tenant_id (from
the JWT query string). Publishing a message routes to all connections for that
tenant. Used by tx_paid, tx_autovoid, low-conf alerts.
"""
import asyncio
from typing import Any

from fastapi import WebSocket


class TenantHub:
    def __init__(self) -> None:
        self._conns: dict[int, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def register(self, tenant_id: int, ws: WebSocket) -> None:
        async with self._lock:
            self._conns.setdefault(tenant_id, set()).add(ws)

    async def unregister(self, tenant_id: int, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._conns.get(tenant_id)
            if conns is not None:
                conns.discard(ws)
                if not conns:
                    self._conns.pop(tenant_id, None)

    async def publish(self, tenant_id: int, message: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._conns.get(tenant_id, ()))
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                pass


hub = TenantHub()
