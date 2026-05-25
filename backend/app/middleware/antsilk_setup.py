"""Builds the AntsilkConfig + RouteRule set + CF-IP shim used by main.py.

Two responsibilities:

1. ``build_antsilk_config()`` — assembles AntsilkConfig with the route rules
   from PLAN-stage3-Geyam.md Phase 7 step 3 (skip rate limit on Stripe /
   Billplz webhooks, allow user-content on /ask, skip body scan on uploads)
   and wires the Postgres sink.

2. ``RealClientIPMiddleware`` — antsilk's ``_client_ip`` reads
   ``scope["client"]`` directly, which on the VPS resolves to Caddy's
   Docker-network IP (172.x). This ASGI shim rewrites ``scope["client"]``
   from the CF-Connecting-IP header (Cloudflare's authoritative client IP)
   so antsilk's rate limiter keys by real client and antsilk_events.ip_address
   contains a real INET, not the Caddy bridge.

   Falls back to X-Forwarded-For (first hop) if CF-Connecting-IP absent — e.g.
   in local docker-compose where Caddy still proxies but CF is not in path.
"""
from __future__ import annotations

import os
from typing import Any, Awaitable, Callable

from antsilk import AntsilkConfig, RouteRule

from app.services.antsilk_postgres_sink import AntsilkPostgresSink

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def build_antsilk_config() -> AntsilkConfig:
    """Default requests_per_minute=60 matches antsilk v0.1.0 defaults; we
    rely on Cloudflare's edge ratelimit (set in Phase 5) for tighter caps
    on /auth/*. Threat intel feeds also use library defaults."""
    return AntsilkConfig(
        sink=AntsilkPostgresSink(),
        route_rules=(
            # Webhooks burst from a single source IP (Stripe/Billplz edge
            # nodes) that may land on public threat feeds. Skip both to
            # guarantee delivery; idempotency + HMAC verification inside
            # the handler is the real guard.
            RouteRule(
                path="/payments/webhook",
                skip_rate_limit=True,
                skip_threat_intel=True,
            ),
            RouteRule(
                path="/payments/webhook/*",
                skip_rate_limit=True,
                skip_threat_intel=True,
            ),
            RouteRule(
                path="/subscriptions/webhook",
                skip_rate_limit=True,
                skip_threat_intel=True,
            ),
            # Healthchecks.io webhook secret in URL; bursts allowed.
            RouteRule(
                path="/alerts/webhook/*",
                skip_rate_limit=True,
                skip_threat_intel=True,
            ),
            # /menu/ask is owner-typed chat — natural language can contain
            # SQLi/XSS-shaped substrings ("or 1=1", "<script>"). Skip the
            # regex pattern scanner; Chenki sees the raw text either way.
            RouteRule(
                path="/menu/ask",
                skip_pattern_scan=True,
            ),
            # File uploads — body scan is a no-op in v0.1.0 (per middleware
            # docstring) but declared so config survives the v0.3.0 upgrade
            # without code change.
            RouteRule(
                path="/menu/upload",
                skip_body_scan=True,
            ),
            RouteRule(
                path="/training/video",
                skip_body_scan=True,
            ),
        ),
    )


class RealClientIPMiddleware:
    """Pure-ASGI shim. Must wrap AntsilkMiddleware on the OUTSIDE so antsilk
    sees the rewritten scope. Does nothing if no trusted IP header found.

    Trusts CF-Connecting-IP unconditionally because UFW + the Caddy
    @not_cf filter (Phase 5) restrict origin :443 to Cloudflare IP ranges;
    anything reaching here without a CF cookie was already triaged.
    """

    def __init__(self, app: ASGIApp, header_priority: tuple[str, ...] = ("cf-connecting-ip", "x-forwarded-for")) -> None:
        self.app = app
        # Pre-encode header names once; ASGI delivers headers as bytes.
        self._headers = tuple(h.lower().encode("latin-1") for h in header_priority)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            real_ip = self._extract(scope)
            if real_ip is not None:
                client = scope.get("client")
                port = client[1] if client else 0
                # Mutating scope["client"] in place is the standard ASGI
                # forwarded-IP pattern (uvicorn does the same with
                # --proxy-headers).
                scope = dict(scope)
                scope["client"] = (real_ip, port)
        await self.app(scope, receive, send)

    def _extract(self, scope: Scope) -> str | None:
        headers = scope.get("headers", [])
        for header_name in self._headers:
            for name, value in headers:
                if name == header_name:
                    text = value.decode("latin-1", errors="replace").strip()
                    # XFF can be "client, proxy1, proxy2" — first wins.
                    first = text.split(",", 1)[0].strip()
                    if first:
                        return first
        return None


def antsilk_enabled() -> bool:
    """Allow disabling antsilk via env for emergency rollback without code change."""
    return os.getenv("ANTSILK_ENABLED", "true").lower() in ("1", "true", "yes")
