"""Stage 2 ORM registrations. Stage 1 models (menu_item, transaction, model_version)
are parked — they will be re-landed tenant-scoped in later phases."""
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.menu_item import MenuItem
from app.models.model_version import ModelVersion
from app.models.openai_usage import OpenAIUsage
from app.models.payment import Payment
from app.models.receipt import Receipt
from app.models.stock_movement import StockMovement
from app.models.tenant import Tenant
from app.models.tenant_settings import TenantSettings
from app.models.training_job import TrainingJob
from app.models.transaction import Transaction, TransactionItem
from app.models.user import User

__all__ = ["Tenant", "User", "AuditLog", "TenantSettings", "MenuItem",
           "TrainingJob", "ModelVersion", "OpenAIUsage", "Customer",
           "Transaction", "TransactionItem", "Payment", "Receipt", "StockMovement"]
