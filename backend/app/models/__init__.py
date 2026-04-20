from app.database import register_tenant_scoped
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.menu_item import MenuItem
from app.models.model_version import ModelVersion
from app.models.openai_usage import OpenAIUsage, PHashCache
from app.models.payment import Payment
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.receipt import Receipt
from app.models.stock_movement import StockMovement
from app.models.supplier import Supplier
from app.models.tenant import Tenant, TenantSettings
from app.models.training_job import TrainingJob
from app.models.transaction import Transaction, TransactionItem
from app.models.user import User

register_tenant_scoped(
    TenantSettings, User, AuditLog, MenuItem, TrainingJob,
    ModelVersion, OpenAIUsage, PHashCache,
    Customer, Transaction, Payment, StockMovement, Receipt,
    Supplier, PurchaseOrder,
)

__all__ = [
    "Tenant", "TenantSettings", "User", "AuditLog", "MenuItem", "TrainingJob",
    "ModelVersion", "OpenAIUsage", "PHashCache",
    "Customer", "Transaction", "TransactionItem", "Payment", "StockMovement",
    "Receipt", "Supplier", "PurchaseOrder", "PurchaseOrderItem",
]
