"""Phase 12: the fan-out hub keeps tenants isolated and drops dead sockets."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import ws_hub  # noqa: E402


class FakeWS:
    def __init__(self, fail: bool = False):
        self.messages: list[str] = []
        self.fail = fail

    async def send_text(self, msg: str) -> None:
        if self.fail:
            raise ConnectionError("dead")
        self.messages.append(msg)


@pytest.mark.asyncio
async def test_broadcast_only_to_matching_tenant():
    # Isolate state between parallel tests.
    ws_hub._connections.clear()
    a1, a2, b1 = FakeWS(), FakeWS(), FakeWS()
    await ws_hub.register(1, a1)
    await ws_hub.register(1, a2)
    await ws_hub.register(2, b1)

    await ws_hub.broadcast(1, "tx_paid", {"tx_id": 42})

    assert len(a1.messages) == 1 and len(a2.messages) == 1
    assert len(b1.messages) == 0
    assert json.loads(a1.messages[0]) == {"type": "tx_paid", "payload": {"tx_id": 42}}


@pytest.mark.asyncio
async def test_dead_socket_is_pruned():
    ws_hub._connections.clear()
    alive, dead = FakeWS(), FakeWS(fail=True)
    await ws_hub.register(7, alive)
    await ws_hub.register(7, dead)

    await ws_hub.broadcast(7, "ping")

    snap = ws_hub._connections_snapshot()
    assert snap.get(7) == 1  # dead was dropped


if __name__ == "__main__":
    asyncio.run(test_broadcast_only_to_matching_tenant())
    asyncio.run(test_dead_socket_is_pruned())
    print("OK")
