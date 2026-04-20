"""Holds the current tenant_id for the request/task in a ContextVar so the
SQLAlchemy event hook can auto-scope every ORM query."""
from contextvars import ContextVar
from typing import Optional

_current_tenant_id: ContextVar[Optional[int]] = ContextVar("current_tenant_id", default=None)

# When True, the event hook is bypassed (used by create_tenant CLI and admin endpoints
# that legitimately span tenants). All other code paths MUST go through a scoped session.
_tenant_scope_bypass: ContextVar[bool] = ContextVar("tenant_scope_bypass", default=False)


def get_current_tenant_id() -> Optional[int]:
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: Optional[int]):
    return _current_tenant_id.set(tenant_id)


def is_scope_bypassed() -> bool:
    return _tenant_scope_bypass.get()


def set_scope_bypass(value: bool):
    return _tenant_scope_bypass.set(value)
