import datetime as dt
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

CART_STATUSES = ("open", "recovered", "expired", "no_contact")


class AbandonedCart(TimestampMixin, Base):
    """A Shopify checkout that was started and not finished. Only a source that sends checkout events (Shopify) can fill this.

    status  open        waiting: still within the reminder plan
            recovered   the customer bought: reminders stop at once
            expired     too old to remind
            no_contact  no customer we may message (no consent or no contact): kept for the numbers, never messaged"""

    __tablename__ = "abandoned_carts"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'recovered', 'expired', 'no_contact')", name="cart_status_known"),
        Index("ix_abandoned_carts_status_updated", "status", "checkout_updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    checkout_id: Mapped[str] = mapped_column(String(60), unique=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    items: Mapped[str | None] = mapped_column(Text)
    total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(8))
    checkout_url: Mapped[str | None] = mapped_column(String(600))
    checkout_updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))     # when the shopper last did something
    status: Mapped[str] = mapped_column(String(12), default="open", server_default="open")
    reminders_sent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_reminder_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    recovered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
