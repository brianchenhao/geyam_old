from app.database import register_tenant_scoped
from app.models.audit_log import AuditLog
from app.models.menu_item import MenuItem
from app.models.model_version import ModelVersion
from app.models.openai_usage import OpenAIUsage, PHashCache
from app.models.tenant import Tenant, TenantSettings
from app.models.training_job import TrainingJob
from app.models.user import User

register_tenant_scoped(
    TenantSettings, User, AuditLog, MenuItem, TrainingJob,
    ModelVersion, OpenAIUsage, PHashCache,
)

__all__ = [
    "Tenant", "TenantSettings", "User", "AuditLog", "MenuItem",
    "TrainingJob", "ModelVersion", "OpenAIUsage", "PHashCache",
]
