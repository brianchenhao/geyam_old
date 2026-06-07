from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProcessedStripeEvent(Base):
    """Idempotency table — webhook handler inserts on success, dupes are no-ops.

    Stripe retries webhooks aggressively; without this, a duplicate
    `invoice.payment_failed` could double-mark a tenant past_due.
    """
    __tablename__ = "processed_stripe_events"
    __tenant_root__ = True  # not tenant-scoped

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
