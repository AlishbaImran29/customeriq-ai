import datetime as dt

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    """Who tried to change something, when, and whether the server allowed it. One row per request that is not just looking.
    It records the ROUTE (for example "POST /api/v1/refunds/{refund_id}/record") and the ids in it, never what was typed:
    no names, phones, emails or message texts end up here. Rows are only ever added."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_at", "at"), Index("ix_audit_log_actor", "actor_email"))

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    actor_email: Mapped[str] = mapped_column(String(320))
    actor_role: Mapped[str] = mapped_column(String(10))
    method: Mapped[str] = mapped_column(String(8))
    route: Mapped[str] = mapped_column(String(200))
    outcome: Mapped[str] = mapped_column(String(10))            # "allowed" | "denied"
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
