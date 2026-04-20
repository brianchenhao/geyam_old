from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    transaction_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("transactions.id", ondelete="CASCADE"), unique=True)
    pdf_path: Mapped[Optional[str]] = mapped_column(Text)
    emailed_to: Mapped[Optional[str]] = mapped_column(String(255))
    emailed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    resend_id: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
