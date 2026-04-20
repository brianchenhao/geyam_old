from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    supplier_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("suppliers.id"))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    expected_at: Mapped[Optional[date]] = mapped_column(Date)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    total_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('draft','sent','partial','received','cancelled')",
                        name="po_status_check"),
    )


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    po_id: Mapped[int] = mapped_column(Integer, ForeignKey("purchase_orders.id", ondelete="CASCADE"))
    menu_item_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("menu_items.id"))
    quantity_ordered: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_received: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
