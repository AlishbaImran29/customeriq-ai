import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MetaEvent(Base):
    """A Purchase event for the Meta Conversions API, one per delivered order. `event_id` is unique, so an order is never sent twice
    (Meta also uses it to de-duplicate against the browser pixel).

    pending   waiting to be sent        sent     Meta accepted it         dry_run  prepared but test mode is on (nothing left the server)
    failed    gave up after retries      skipped  not sent on purpose (the customer did not agree, or no usable contact)"""

    __tablename__ = "meta_events"
    __table_args__ = (CheckConstraint("status IN ('pending', 'sent', 'dry_run', 'failed', 'skipped')", name="meta_event_status_known"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(String(200))
    event_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
