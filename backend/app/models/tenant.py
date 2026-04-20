from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    handle: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    settings: Mapped["TenantSettings"] = relationship(
        back_populates="tenant", uselist=False, cascade="all, delete-orphan"
    )


class TenantSettings(Base):
    __tablename__ = "tenant_settings"

    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    # Fernet-encrypted — ciphertext is ~1.6× plain length, so Text avoids truncation
    billplz_api_key: Mapped[str | None] = mapped_column(Text)
    billplz_collection_id: Mapped[str | None] = mapped_column(String(100))
    billplz_xsign_key: Mapped[str | None] = mapped_column(Text)
    billplz_mode: Mapped[str] = mapped_column(String(10), default="sandbox")
    logo_path: Mapped[str | None] = mapped_column(Text)
    receipt_footer: Mapped[str] = mapped_column(
        Text, default="Thank you! Goods sold are not refundable."
    )
    shop_contact_email: Mapped[str | None] = mapped_column(String(255))
    shop_contact_phone: Mapped[str | None] = mapped_column(String(30))
    yolo_conf_threshold: Mapped[float] = mapped_column(Numeric(3, 2), default=0.60)
    yolo_conf_minimum: Mapped[float] = mapped_column(Numeric(3, 2), default=0.40)
    openai_daily_limit: Mapped[int] = mapped_column(Integer, default=50)
    training_locked_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tenant: Mapped[Tenant] = relationship(back_populates="settings")
