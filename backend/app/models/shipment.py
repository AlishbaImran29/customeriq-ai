import datetime as dt
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# The four states of a parcel. "delivered" and "returned" are the closed ones: they have a result and a date.
STATUS_DELIVERED = "delivered"
STATUS_RETURNED = "returned"
STATUS_IN_TRANSIT = "in_transit"
STATUS_LOST = "lost"
STATUSES = (STATUS_DELIVERED, STATUS_RETURNED, STATUS_IN_TRANSIT, STATUS_LOST)
CLOSED_STATUSES = (STATUS_DELIVERED, STATUS_RETURNED)

# Marks shipments made up for a demo, so they can always be told apart from real ones and deleted.
SOURCE_DEMO = "demo (synthetic)"


class Shipment(TimestampMixin, Base):
    """One parcel handed to a courier: who carried it, where to, and what happened.

    `order_id` links it to the order it carries when that can be worked out; a shipment with no
    link is still kept and still counts in the courier figures.
    """

    __tablename__ = "shipments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('delivered', 'returned', 'in_transit', 'lost')", name="shipment_status_known"
        ),
        CheckConstraint("closed_date IS NULL OR closed_date >= booked_date", name="shipment_dates_in_order"),
        CheckConstraint("cod_amount IS NULL OR cod_amount >= 0", name="shipment_cod_non_negative"),
        CheckConstraint("courier_fee IS NULL OR courier_fee >= 0", name="shipment_fee_non_negative"),
        Index("ix_shipments_courier_city", "courier", "city"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    # A fingerprint of the shipment (see services/shipment_import.py), so a file can be imported again.
    external_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    courier: Mapped[str] = mapped_column(String(60), index=True)             # the standard name ("TCS")
    courier_raw: Mapped[str | None] = mapped_column(String(100))             # as it was written ("t.c.s ")
    city: Mapped[str | None] = mapped_column(String(100), index=True)
    city_raw: Mapped[str | None] = mapped_column(String(100))
    booked_date: Mapped[dt.date] = mapped_column(Date, index=True)
    closed_date: Mapped[dt.date | None] = mapped_column(Date)                # the day it was delivered or came back
    status: Mapped[str] = mapped_column(String(12))
    return_reason: Mapped[str | None] = mapped_column(Text)
    refused: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")  # "refused by customer"
    cod_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    courier_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    source: Mapped[str | None] = mapped_column(String(30))                   # "import", "quick_order" or SOURCE_DEMO
