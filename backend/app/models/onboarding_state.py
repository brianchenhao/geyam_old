from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OnboardingState(Base):
    """Per-tenant signup wizard progress. One row created on tenant signup
    (Phase 10) and advanced as the owner completes each step.

    step values:
      1 = shop + logo
      2 = first cashier
      3 = sample items
      4 = billing intro
      5 = done

    Lets the UI resume the wizard if the owner drops off mid-flow.
    """
    __tablename__ = "onboarding_state"

    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True,
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    shop_info_done: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    cashier_done: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    items_done: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    billing_seen: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("step BETWEEN 1 AND 5", name="onboarding_state_step_check"),
    )
