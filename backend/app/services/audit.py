"""Audit helpers.

Two surfaces:

1. ``audit()`` — Stage 2 helper that appends to ``audit_logs`` (tenant-scoped
   activity, e.g. inventory adjustments, cashier resets). Caller owns commit.

2. ``write_audit_event()`` + ``@audited`` — Stage 3 Phase 9 helpers that write
   to ``admin_audit_log`` (the non-repudiation trail of admin / system actions).
   The decorator captures actor / IP / request_id automatically and runs the
   audit insert on a *fresh* session so a failure in the wrapped function still
   produces a row (success=false). Audit-on-failure is the whole point.
"""
from __future__ import annotations

import functools
import inspect
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal
from app.models.admin_audit_log import AdminAuditLog
from app.models.audit_log import AuditLog
from app import tenant_context

log = logging.getLogger(__name__)

# ----- Stage 2 helper (kept for backwards compatibility) ---------------------


async def audit(
    session: AsyncSession,
    *,
    action: str,
    tenant_id: Optional[int] = None,
    user_id: Optional[int] = None,
    entity: Optional[str] = None,
    entity_id: Optional[int] = None,
    meta: Optional[dict[str, Any]] = None,
) -> None:
    session.add(AuditLog(
        action=action, tenant_id=tenant_id, user_id=user_id,
        entity=entity, entity_id=entity_id, meta=meta,
    ))


# ----- Phase 9 admin audit ---------------------------------------------------


def _jsonable(v: Any) -> Any:
    """Best-effort JSON-safe conversion for JSONB. SQLAlchemy serialises through
    psycopg's JSONB codec which uses json.dumps — Decimals, datetimes, UUIDs all
    need stringifying. Whatever survives ``str()`` is fine."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    # Pydantic model
    dump = getattr(v, "model_dump", None)
    if callable(dump):
        try:
            return _jsonable(dump(mode="json"))
        except TypeError:
            return _jsonable(dump())
    try:
        json.dumps(v)
        return v
    except Exception:
        return str(v)


async def write_audit_event(
    session: AsyncSession,
    *,
    actor_email: str,
    action: str,
    tenant_id: Optional[int] = None,
    actor_ip: Optional[str] = None,
    before_data: Optional[dict[str, Any]] = None,
    after_data: Optional[dict[str, Any]] = None,
    request_id: Optional[str] = None,
    success: bool = True,
) -> None:
    """Append one row to ``admin_audit_log``. Caller owns commit."""
    session.add(AdminAuditLog(
        actor_email=actor_email,
        actor_ip=actor_ip,
        tenant_id=tenant_id,
        action=action,
        before_data=_jsonable(before_data) if before_data is not None else None,
        after_data=_jsonable(after_data) if after_data is not None else None,
        request_id=request_id,
        success=success,
    ))


# ----- @audited decorator ----------------------------------------------------

BeforeLoader = Callable[[AsyncSession, dict[str, Any]], Awaitable[Optional[dict[str, Any]]]]
AfterExtractor = Callable[[Any, dict[str, Any]], Optional[dict[str, Any]]]
TenantResolver = Callable[[dict[str, Any]], Optional[int]]
ActorResolver = Callable[[dict[str, Any]], Optional[str]]


def _default_actor(kwargs: dict[str, Any]) -> Optional[str]:
    """Look for an email in the usual places: admin dep, then user claims."""
    for key in ("admin", "admin_claims", "user_claims", "user", "current_user"):
        v = kwargs.get(key)
        if isinstance(v, dict) and v.get("email"):
            return v["email"]
    return None


def _default_tenant(kwargs: dict[str, Any]) -> Optional[int]:
    """Path / body parameter named ``tenant_id`` wins; fall back to the contextvar."""
    if isinstance(kwargs.get("tenant_id"), int):
        return kwargs["tenant_id"]
    return tenant_context.get_current_tenant_id()


def _default_after(result: Any, kwargs: dict[str, Any]) -> Optional[dict[str, Any]]:
    if result is None:
        return None
    if isinstance(result, dict):
        return result
    dump = getattr(result, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except TypeError:
            return dump()
    return {"result": _jsonable(result)}


async def _write_audit_isolated(**fields: Any) -> None:
    """Write the audit row on a *fresh* session with tenant-scope bypass.
    Used so an audit insert never fails because the caller's session is in a
    rolled-back state, and so failure audits land even when the work session
    is unusable."""
    try:
        async with SessionLocal() as s:
            async with bypass_for_audit():
                await write_audit_event(s, **fields)
                await s.commit()
    except Exception:
        log.exception("admin_audit_log insert failed (action=%s)", fields.get("action"))


def bypass_for_audit():
    """Tiny wrapper so this module doesn't import from app.deps (avoids cycles)."""
    from app.deps import bypass_tenant_scope
    return bypass_tenant_scope()


def audited(
    action: str,
    *,
    static_actor: Optional[str] = None,
    before: Optional[BeforeLoader] = None,
    after: Optional[AfterExtractor] = None,
    tenant_resolver: Optional[TenantResolver] = None,
    actor_resolver: Optional[ActorResolver] = None,
) -> Callable:
    """Decorator that wraps a FastAPI endpoint and writes an admin_audit_log row.

    Requirements on the wrapped function's signature:
      - ``request: Request`` (for client IP + X-Request-Id)
      - ``session: AsyncSession`` (used by the optional ``before`` loader)
      - one of: ``admin``, ``admin_claims``, ``user_claims``, ``user``
        (dict with ``email``) — OR set ``static_actor=`` on the decorator
        (for webhook / cron handlers that have no JWT).

    Captures:
      - actor_email — admin/user dict email (or static_actor)
      - actor_ip — request.client.host (already CF-Connecting-IP-rewritten
        by RealClientIPMiddleware in main.py)
      - request_id — X-Request-Id header (None if absent)
      - before_data — result of optional ``before(session, kwargs)`` callback
      - after_data — wrapped function's return value (Pydantic .model_dump
        preferred), or ``after(result, kwargs)`` if supplied

    On exception: writes a success=False row with before_data + no after_data,
    then re-raises. The audit row goes through a fresh session so a rolled-back
    caller session does not lose the audit trail.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request: Optional[Request] = kwargs.get("request")
            session: Optional[AsyncSession] = kwargs.get("session")

            actor_email = (
                (actor_resolver(kwargs) if actor_resolver else None)
                or static_actor
                or _default_actor(kwargs)
                or "unknown"
            )
            tenant_id = (
                tenant_resolver(kwargs) if tenant_resolver
                else _default_tenant(kwargs)
            )
            actor_ip = None
            request_id = None
            if request is not None:
                if request.client is not None:
                    actor_ip = request.client.host
                request_id = request.headers.get("x-request-id")

            before_data: Optional[dict[str, Any]] = None
            if before is not None and session is not None:
                try:
                    before_data = await before(session, kwargs)
                except Exception:
                    log.exception("audited(%s) before-loader raised; continuing", action)

            try:
                result = await fn(*args, **kwargs)
            except Exception:
                await _write_audit_isolated(
                    actor_email=actor_email, action=action, tenant_id=tenant_id,
                    actor_ip=actor_ip, before_data=before_data, after_data=None,
                    request_id=request_id, success=False,
                )
                raise

            after_data = (after(result, kwargs) if after else _default_after(result, kwargs))
            await _write_audit_isolated(
                actor_email=actor_email, action=action, tenant_id=tenant_id,
                actor_ip=actor_ip, before_data=before_data, after_data=after_data,
                request_id=request_id, success=True,
            )
            return result

        # Preserve the original signature so FastAPI's dependency-injection
        # introspection sees the real parameters, not (*args, **kwargs).
        # eval_str=True resolves PEP-563 string annotations against fn.__globals__
        # at decoration time — without it, FastAPI later tries to resolve them
        # against the wrapper's globals (this module) and fails on classes that
        # only exist in the decorated module.
        wrapper.__signature__ = inspect.signature(fn, eval_str=True)  # type: ignore[attr-defined]
        wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
        return wrapper

    return decorator
