from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "tx_number", name="uq_tx_tenant_number"),
        CheckConstraint("status IN ('pending','paid','voided')", name="ck_tx_status"),
        Index("idx_tx_tenant_date", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    tx_number: Mapped[str] = mapped_column(String(30), nullable=False)
    staff_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    customer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("customers.id"))
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), default="qr")
    payment_ref: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)
    voided_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))

    items: Mapped[list["TransactionItem"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan"
    )


class TransactionItem(Base):
    __tablename__ = "transaction_items"
    __table_args__ = (
        CheckConstraint(
            "source IN ('yolo','yolo_low','mediapipe','openai','openai.fresh','openai.cache','manual')",
            name="ck_tx_item_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("transactions.id", ondelete="CASCADE")
    )
    menu_item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("menu_items.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    source: Mapped[str | None] = mapped_column(String(20))

    transaction: Mapped[Transaction] = relationship(back_populates="items")
