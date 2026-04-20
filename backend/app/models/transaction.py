from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    tx_number: Mapped[str] = mapped_column(String(30), nullable=False)
    staff_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    customer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("customers.id"))
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), default="qr")
    payment_ref: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    voided_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    voided_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "tx_number", name="tx_tenant_number_key"),
        CheckConstraint("status IN ('pending','paid','voided')", name="tx_status_check"),
    )


class TransactionItem(Base):
    __tablename__ = "transaction_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(Integer, ForeignKey("transactions.id", ondelete="CASCADE"))
    menu_item_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("menu_items.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    source: Mapped[Optional[str]] = mapped_column(String(20))
