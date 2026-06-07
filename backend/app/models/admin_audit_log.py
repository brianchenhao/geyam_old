from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdminAuditLog(Base):
    """Append-only non-repudiation log of admin actions.

    Distinct from `audit_logs` (which is tenant-scoped activity from Stage 2).
    This table is admin/system-actor scoped and survives tenant deletion
    (tenant_id ON DELETE SET NULL) so the trail of "who did what" is preserved
    even if the tenant row is purged.
    """
    __tablename__ = "admin_audit_log"
    __tenant_root__ = True  # exempt from the tenant-scope hook (admins read across all tenants)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True,
    )
    actor_email: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    actor_ip: Mapped[Optional[str]] = mapped_column(INET)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="SET NULL"),
    )
    action: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    before_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    after_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    request_id: Mapped[Optional[str]] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
