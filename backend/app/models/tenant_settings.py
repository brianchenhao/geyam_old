from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TenantSettings(Base):
    __tablename__ = "tenant_settings"

    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    # Encrypted-at-rest Billplz credentials (Fernet ciphertext — NEVER returned raw over API)
    billplz_api_key: Mapped[Optional[str]] = mapped_column(String(512))
    billplz_collection_id: Mapped[Optional[str]] = mapped_column(String(100))
    billplz_xsign_key: Mapped[Optional[str]] = mapped_column(String(512))
    billplz_mode: Mapped[str] = mapped_column(String(10), default="sandbox")

    logo_path: Mapped[Optional[str]] = mapped_column(Text)
    receipt_footer: Mapped[Optional[str]] = mapped_column(
        Text, default="Thank you! Goods sold are not refundable."
    )
    shop_contact_email: Mapped[Optional[str]] = mapped_column(String(255))
    shop_contact_phone: Mapped[Optional[str]] = mapped_column(String(30))

    yolo_conf_threshold: Mapped[float] = mapped_column(Float, default=0.60)
    yolo_conf_minimum: Mapped[float] = mapped_column(Float, default=0.40)
    openai_daily_limit: Mapped[int] = mapped_column(Integer, default=50)

    training_locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
