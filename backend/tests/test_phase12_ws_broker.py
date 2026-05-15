"""Phase 12 — Redis pub/sub bridge: serialization + forwarding contract."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.services import ws_broker


def test_publish_sync_formats_payload(monkeypatch):
    captured = {}

    class FakeClient:
        def publish(self, channel, payload):
            captured["channel"] = channel
            captured["payload"] = payload

        @classmethod
        def from_url(cls, _url):
            return cls()

    monkeypatch.setattr(ws_broker.sync_redis, "Redis", FakeClient)

    ws_broker.publish_sync(7, {"type": "tx_autovoid", "tx_id": 99})

    assert captured["channel"] == ws_broker.CHANNEL
    data = json.loads(captured["payload"])
    assert data == {"tenant_id": 7, "message": {"type": "tx_autovoid", "tx_id": 99}}


def test_publish_sync_swallows_redis_errors(monkeypatch, capsys):
    class ExplodingClient:
        @classmethod
        def from_url(cls, _url):
            raise RuntimeError("redis down")

    monkeypatch.setattr(ws_broker.sync_redis, "Redis", ExplodingClient)

    # Must not raise — scheduler/worker should keep running.
    ws_broker.publish_sync(1, {"type": "x"})

    out = capsys.readouterr().out
    assert "ws_broker" in out
