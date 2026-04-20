from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(50))
    barcode: Mapped[Optional[str]] = mapped_column(String(64))
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    reorder_point: Mapped[int] = mapped_column(Integer, default=5)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=0)
    image_path: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    frame_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "label", name="menu_items_tenant_label_key"),
        UniqueConstraint("tenant_id", "name", name="menu_items_tenant_name_key"),
    )
