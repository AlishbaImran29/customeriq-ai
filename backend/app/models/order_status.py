"""Order status history (Auto Messenger part 2) and the record of webhook calls already handled."""

import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

ORDER_STATUSES = ("confirmed", "dispatched", "in_transit", "out_for_delivery", "delivered", "returned")
STATUS_SOURCES = ("shopify", "courier_import", "manual", "system")


class OrderStatusHistory(Base):
    """One step in an order's life. The CURRENT status is the latest row; nothing here is ever rewritten."""

    __tablename__ = "order_status_history"
    __table_args__ = (
        CheckConstraint("status IN ('confirmed', 'dispatched', 'in_transit', 'out_for_delivery', 'delivered', 'returned')", name="order_status_known"),
        CheckConstraint("source IN ('shopify', 'courier_import', 'manual', 'system')", name="order_status_source_known"),
        Index("ix_order_status_history_order_at", "order_id", "at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))                  # when it happened (not when it was recorded)
    source: Mapped[str] = mapped_column(String(20))
    courier: Mapped[str | None] = mapped_column(String(60))
    tracking_number: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(String(200))
    recorded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookEvent(Base):
    """A webhook call that was already handled, so a retry from the sender never does the work twice."""

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("source", "event_id", name="uq_webhook_events_source_event"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20))
    event_id: Mapped[str] = mapped_column(String(120))
    received_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
