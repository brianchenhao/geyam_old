"""Phase 12 — unit test for TenantHub: per-tenant isolation + publish fans out."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.websocket import TenantHub


class FakeWS:
    def __init__(self):
        self.received: list[dict] = []

    async def send_json(self, msg):
        self.received.append(msg)


@pytest.mark.asyncio
async def test_publish_reaches_only_same_tenant():
    hub = TenantHub()
    a1, a2, b1 = FakeWS(), FakeWS(), FakeWS()
    await hub.register(1, a1)
    await hub.register(1, a2)
    await hub.register(2, b1)

    await hub.publish(1, {"type": "tx_paid", "tx_id": 42})

    assert a1.received == [{"type": "tx_paid", "tx_id": 42}]
    assert a2.received == [{"type": "tx_paid", "tx_id": 42}]
    assert b1.received == []


@pytest.mark.asyncio
async def test_unregister_stops_delivery():
    hub = TenantHub()
    ws = FakeWS()
    await hub.register(1, ws)
    await hub.unregister(1, ws)
    await hub.publish(1, {"type": "x"})
    assert ws.received == []


@pytest.mark.asyncio
async def test_publish_survives_broken_socket():
    class BrokenWS:
        async def send_json(self, _):
            raise RuntimeError("boom")

    hub = TenantHub()
    good = FakeWS()
    await hub.register(1, BrokenWS())
    await hub.register(1, good)
    await hub.publish(1, {"type": "ok"})
    assert good.received == [{"type": "ok"}]
