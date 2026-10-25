import datetime as dt
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class BusinessSettings(TimestampMixin, Base):
    """The shop's own cost numbers for the profit figures. One row. NULL means "the seller has not entered it"
    (which the profit page says out loud) and is never silently treated as a real zero."""

    __tablename__ = "business_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    packing_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))            # per order: box, tape, label
    return_shipping_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))    # extra cost of a parcel coming back


class AdSpend(TimestampMixin, Base):
    """Money spent on ads on one day, for one sales channel (and optionally one campaign). Typed in, imported from a file,
    or (later) pulled from Meta. The profit page shares each channel's spend over that channel's orders: an ESTIMATE."""

    __tablename__ = "ad_spend"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ad_spend_non_negative"),
        CheckConstraint("channel IN ('instagram', 'whatsapp', 'facebook', 'website', 'other')", name="ad_spend_channel_known"),
        Index("ix_ad_spend_date_channel", "spend_date", "channel"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    spend_date: Mapped[dt.date] = mapped_column(Date)
    channel: Mapped[str] = mapped_column(String(20))
    campaign: Mapped[str | None] = mapped_column(String(160))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    source: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual")      # manual | csv | meta
    # What Meta itself reported for that row (from its export or the Marketing API). NULL = not known. Compared with real results.
    meta_purchases: Mapped[int | None] = mapped_column(Integer)
    meta_revenue: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
