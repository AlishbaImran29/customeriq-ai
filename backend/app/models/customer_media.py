"""Customer videos and photos (Auto Messenger part 3), received on WhatsApp after a delivery."""

import datetime as dt

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CustomerMedia(TimestampMixin, Base):
    """One video or image a customer sent. The file itself lives in a PRIVATE storage bucket (`storage_path`).

    It may be used in ads only when BOTH are true: the customer answered YES to "may we share it?" and the seller
    marked it usable. The database itself refuses `usable_in_ads` without a yes (see the check constraint).
    """

    __tablename__ = "customer_media"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'stored', 'rejected', 'failed')", name="media_status_known"),
        CheckConstraint("share_answer IN ('pending', 'yes', 'no')", name="media_answer_known"),
        CheckConstraint("kind IN ('image', 'video')", name="media_kind_known"),
        CheckConstraint("NOT usable_in_ads OR share_answer = 'yes'", name="media_usable_needs_yes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), index=True)
    incoming_message_id: Mapped[int | None] = mapped_column(ForeignKey("incoming_messages.id", ondelete="SET NULL"), unique=True)
    media_id: Mapped[str] = mapped_column(String(128))                      # WhatsApp's id, used to download it
    kind: Mapped[str] = mapped_column(String(10))
    mime_type: Mapped[str | None] = mapped_column(String(80))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    storage_path: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), default="pending", server_default="pending", index=True)
    error: Mapped[str | None] = mapped_column(String(200))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    question_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")   # "may we share it?" was asked
    share_answer: Mapped[str] = mapped_column(String(7), default="pending", server_default="pending")
    usable_in_ads: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    usable_marked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
