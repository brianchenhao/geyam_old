from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    transaction_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("transactions.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(20), default="billplz")
    bill_id: Mapped[Optional[str]] = mapped_column(String(100))
    bill_url: Mapped[Optional[str]] = mapped_column(Text)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    state: Mapped[Optional[str]] = mapped_column(String(20))
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    raw_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
