import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

COD_STATES = ("awaiting", "confirmed", "cancelled", "needs_call")


class CodConfirmation(TimestampMixin, Base):
    """The "do you really want this cash-on-delivery order?" check for one order.

    awaiting -> the customer was asked on WhatsApp and has not answered yet
    confirmed / cancelled -> the customer answered YES / NO (or the seller recorded the result of a phone call)
    needs_call -> nobody answered in time: the seller should phone the customer, and the order's risk is raised"""

    __tablename__ = "cod_confirmations"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_cod_confirmations_order"),
        CheckConstraint("state IN ('awaiting', 'confirmed', 'cancelled', 'needs_call')", name="cod_state_known"),
        CheckConstraint("resolved_by IS NULL OR resolved_by IN ('customer', 'seller')", name="cod_resolved_by_known"),
        Index("ix_cod_confirmations_state_deadline", "state", "deadline_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(String(12), default="awaiting")
    asked_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(10))
    reply_text: Mapped[str | None] = mapped_column(String(200))
