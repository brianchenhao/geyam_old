from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OpenAIUsage(Base):
    __tablename__ = "openai_usage"
    __table_args__ = (UniqueConstraint("tenant_id", "day", name="uq_openai_tenant_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    calls: Mapped[int] = mapped_column(Integer, default=0)


class PHashCache(Base):
    __tablename__ = "phash_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    phash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    result_json: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("tenant_id", "phash", name="uq_phash_tenant_hash"),)
