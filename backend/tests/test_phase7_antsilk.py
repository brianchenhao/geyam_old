"""Phase 7 — unit tests for the Antsilk integration.

End-to-end attack tests run against the live VPS; this file covers the two
load-bearing pieces of glue we own:

1. RealClientIPMiddleware: rewrites scope["client"] from CF-Connecting-IP
   (then X-Forwarded-For first hop), leaves non-http scopes alone.

2. AntsilkPostgresSink: swallows DSN/connection errors so a broken sink
   cannot turn into a 500 for legitimate traffic — explicit anti-mistake
   habit from PLAN-stage3-Geyam.md.

The route-rule config is asserted shape-only — the actual rule evaluation
is antsilk's responsibility (covered by its own tests).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from antsilk import Event

from app.middleware.antsilk_setup import (
    RealClientIPMiddleware,
    build_antsilk_config,
)
from app.services.antsilk_postgres_sink import AntsilkPostgresSink


# ---------- RealClientIPMiddleware ----------------------------------------

class _Sentinel:
    """Captures scope of the inner call so we can assert what the WAF sees."""

    def __init__(self) -> None:
        self.last_scope: dict | None = None

    async def __call__(self, scope, receive, send):
        self.last_scope = scope


async def _drive(mw, scope):
    async def _recv():
        return {"type": "http.disconnect"}

    async def _send(_msg):
        pass

    await mw(scope, _recv, _send)


def _http_scope(headers=(), client=("172.18.0.5", 50001)):
    return {
        "type": "http",
        "method": "GET",
        "path": "/healthz",
        "headers": list(headers),
        "client": client,
    }


@pytest.mark.asyncio
async def test_cf_connecting_ip_rewrites_client():
    inner = _Sentinel()
    mw = RealClientIPMiddleware(inner)
    scope = _http_scope(headers=[(b"cf-connecting-ip", b"203.0.113.7")])
    await _drive(mw, scope)
    assert inner.last_scope["client"] == ("203.0.113.7", 50001)


@pytest.mark.asyncio
async def test_xff_first_hop_used_when_cf_absent():
    inner = _Sentinel()
    mw = RealClientIPMiddleware(inner)
    scope = _http_scope(headers=[(b"x-forwarded-for", b"198.51.100.4, 10.0.0.1")])
    await _drive(mw, scope)
    assert inner.last_scope["client"] == ("198.51.100.4", 50001)


@pytest.mark.asyncio
async def test_cf_wins_over_xff():
    inner = _Sentinel()
    mw = RealClientIPMiddleware(inner)
    scope = _http_scope(headers=[
        (b"x-forwarded-for", b"198.51.100.4"),
        (b"cf-connecting-ip", b"203.0.113.7"),
    ])
    await _drive(mw, scope)
    assert inner.last_scope["client"] == ("203.0.113.7", 50001)


@pytest.mark.asyncio
async def test_no_header_leaves_scope_untouched():
    inner = _Sentinel()
    mw = RealClientIPMiddleware(inner)
    scope = _http_scope()
    original_client = scope["client"]
    await _drive(mw, scope)
    assert inner.last_scope["client"] == original_client


@pytest.mark.asyncio
async def test_websocket_scope_passes_through():
    inner = _Sentinel()
    mw = RealClientIPMiddleware(inner)
    scope = {
        "type": "websocket",
        "client": ("172.18.0.5", 50001),
        "headers": [(b"cf-connecting-ip", b"203.0.113.7")],
    }
    await _drive(mw, scope)
    # No rewrite for websockets — antsilk only inspects http anyway.
    assert inner.last_scope["client"] == ("172.18.0.5", 50001)


# ---------- AntsilkPostgresSink -------------------------------------------

def _fake_event() -> Event:
    return Event.now(
        ip_address="203.0.113.99",
        method="GET",
        path="/foo?id=1' OR '1'='1",
        rule_triggered="sqli",
        severity="high",
        response_code=403,
        user_agent="curl/8",
        event_data={"matched": "OR '1'='1"},
    )


def test_sink_swallows_connection_errors(caplog):
    """A bad DSN should NOT raise — sink failures must never propagate."""
    sink = AntsilkPostgresSink(dsn="postgresql://nobody@127.0.0.1:1/no_such_db")
    # Must not raise.
    sink.write(_fake_event())
    # And we should have logged the failure for ops to see.
    assert any("AntsilkPostgresSink write failed" in r.message for r in caplog.records)


# ---------- Config sanity --------------------------------------------------

def test_route_rules_carve_outs_present():
    cfg = build_antsilk_config()
    by_path = {r.path: r for r in cfg.route_rules}

    # Webhooks: rate_limit + threat_intel skipped (avoid blocking bursty
    # Stripe/Billplz/HC callbacks).
    for p in ("/payments/webhook", "/subscriptions/webhook"):
        assert by_path[p].skip_rate_limit
        assert by_path[p].skip_threat_intel

    # Chat: pattern scan skipped (natural language matches SQLi/XSS regexes).
    assert by_path["/menu/ask"].skip_pattern_scan

    # Uploads: body scan flag set for forward-compat with antsilk v0.3.0.
    for p in ("/menu/upload", "/training/video"):
        assert by_path[p].skip_body_scan
