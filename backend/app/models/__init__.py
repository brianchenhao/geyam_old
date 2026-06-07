"""ORM registrations. Adding a model here ensures Base.registry knows about it
so the tenant-scope hook can iterate mappers."""
from app.models.admin_audit_log import AdminAuditLog
from app.models.audit_log import AuditLog
from app.models.menu_item import MenuItem
from app.models.model_version import ModelVersion
from app.models.onboarding_state import OnboardingState
from app.models.openai_usage import OpenAIUsage
from app.models.payment import Payment
from app.models.processed_stripe_event import ProcessedStripeEvent
from app.models.receipt import Receipt
from app.models.stock_movement import StockMovement
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.models.tenant_settings import TenantSettings
from app.models.training_job import TrainingJob
from app.models.transaction import Transaction, TransactionItem
from app.models.user import User

__all__ = ["Tenant", "User", "AuditLog", "TenantSettings", "MenuItem",
           "TrainingJob", "ModelVersion", "OpenAIUsage",
           "Transaction", "TransactionItem", "Payment", "Receipt",
           "StockMovement",
           "Subscription", "AdminAuditLog", "ProcessedStripeEvent",
           "OnboardingState"]
