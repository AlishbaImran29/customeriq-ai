import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CustomerAudit(Base):
    """A record that something important happened to a customer: edited, merged with another, anonymised or deleted.
    Rows are only added. They never hold a name, phone or email (only counts and the customer's id), so the record
    can stay after the customer's personal data is erased."""

    __tablename__ = "customer_audit"
    __table_args__ = (
        CheckConstraint("action IN ('edit', 'merge', 'anonymise', 'delete')", name="audit_action_known"),
        Index("ix_customer_audit_at", "at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(12))
    customer_ref: Mapped[str] = mapped_column(String(100))       # the customer's id in the app (no personal data)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
