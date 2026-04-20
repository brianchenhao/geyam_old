from app.database import register_tenant_scoped
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant, TenantSettings
from app.models.user import User

register_tenant_scoped(TenantSettings, User, AuditLog)

__all__ = ["Tenant", "TenantSettings", "User", "AuditLog"]
