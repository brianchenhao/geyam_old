from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Subscription(Base):
    """Local cache of Stripe subscription state. Source of truth is Stripe.

    One row per tenant (backfilled by migration 0016 for every Stage 2 tenant on
    the free plan). Webhook handler updates `plan`/`status`/`current_period_end`
    in response to Stripe events.
    """
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(Text)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    plan: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    past_due_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
