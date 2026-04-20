from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OpenAIUsage(Base):
    __tablename__ = "openai_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    calls: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("tenant_id", "day", name="openai_usage_tenant_day_key"),)
