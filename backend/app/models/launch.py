"""Launch Studio tables: a product idea being taken to market, the Google Trends files uploaded for it,
and a small cache so the same AI question is never paid for twice."""

import datetime as dt
import uuid

from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# The life of a launch project. "idea" is where every project starts.
STATUSES = ("idea", "sourcing", "ready", "launched", "dropped")


class LaunchProject(TimestampMixin, Base):
    """One product idea the seller is taking from "I think this could sell" to launched.

    There is no store_id: the whole app works on one shared set of data (there are no separate stores),
    so a project only remembers WHO created it.
    """

    __tablename__ = "launch_projects"
    __table_args__ = (
        CheckConstraint("status IN ('idea', 'sourcing', 'ready', 'launched', 'dropped')", name="launch_status_known"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(12), default="idea", server_default="idea")
    notes: Mapped[str | None] = mapped_column(Text)
    launched_on: Mapped[dt.date | None] = mapped_column(Date)            # set in the last step
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))     # the user who made it
    # Step 2: the vendor whose quote the seller chose (also how a vendor's return rate is worked out).
    chosen_vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"))
    # Step 5: the profit check inputs the seller last saved, so the launch page can compare real results with them.
    profit_inputs: Mapped[dict | None] = mapped_column(JSONB)


class TrendUpload(TimestampMixin, Base):
    """A Google Trends CSV the seller downloaded and uploaded, kept in parsed form.

    Google Trends has no free official API for this, and scraping it is not allowed, so the seller
    exports the file from trends.google.com themselves and the app only reads that file.
    """

    __tablename__ = "trend_uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    launch_project_id: Mapped[int | None] = mapped_column(ForeignKey("launch_projects.id", ondelete="CASCADE"), index=True)
    keyword: Mapped[str] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(60))
    granularity: Mapped[str | None] = mapped_column(String(8))           # "day", "week" or "month"
    points: Mapped[list | None] = mapped_column(JSONB)                   # [["2026-01-04", 45.0], ...] (0-100 interest)
    related: Mapped[list | None] = mapped_column(JSONB)                  # [{"query": ..., "value": ..., "kind": "top"|"rising"}]
    label: Mapped[str | None] = mapped_column(String(12))                # rising / stable / falling / None = not enough data
    ratio: Mapped[float | None]                                          # recent average / earlier average, for the label


class AiCache(TimestampMixin, Base):
    """An AI answer kept under a fingerprint of the question, so asking again is free."""

    __tablename__ = "ai_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)       # sha256 of kind + inputs
    kind: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSONB)


class LaunchProduct(TimestampMixin, Base):
    """A product name in the seller's own data that belongs to a launch project (step 6).

    Matching is by NAME (case-insensitive) against the product names on orders and in product sales.
    """

    __tablename__ = "launch_products"
    __table_args__ = (UniqueConstraint("launch_project_id", "name_key", name="uq_launch_products_project_product"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    launch_project_id: Mapped[int] = mapped_column(ForeignKey("launch_projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    name_key: Mapped[str] = mapped_column(String(120))              # lower case, for matching


class Vendor(TimestampMixin, Base):
    """A supplier the seller talks to. The phone is stored as +92XXXXXXXXXX so a WhatsApp link always works."""

    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    whatsapp_phone: Mapped[str | None] = mapped_column(String(13))
    city: Mapped[str | None] = mapped_column(String(100))
    categories: Mapped[str | None] = mapped_column(String(300))     # free text, comma separated
    notes: Mapped[str | None] = mapped_column(Text)


class VendorQuote(TimestampMixin, Base):
    """What a vendor offered for one launch project."""

    __tablename__ = "vendor_quotes"
    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="quote_price_non_negative"),
        CheckConstraint("moq IS NULL OR moq >= 1", name="quote_moq_positive"),
        CheckConstraint("delivery_days IS NULL OR delivery_days >= 0", name="quote_days_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), index=True)
    launch_project_id: Mapped[int] = mapped_column(ForeignKey("launch_projects.id", ondelete="CASCADE"), index=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    moq: Mapped[int | None] = mapped_column(Integer)                # minimum order quantity
    delivery_days: Mapped[int | None] = mapped_column(Integer)
    quality_notes: Mapped[str | None] = mapped_column(Text)
    sample_received: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    quoted_on: Mapped[dt.date] = mapped_column(Date)


class CompetitorAd(TimestampMixin, Base):
    """An ad the seller saw on the Meta Ad Library website and chose to save.

    The seller views ads on the website and types or pastes what they want to keep. The app never scrapes it.
    """

    __tablename__ = "competitor_ads"

    id: Mapped[int] = mapped_column(primary_key=True)
    launch_project_id: Mapped[int] = mapped_column(ForeignKey("launch_projects.id", ondelete="CASCADE"), index=True)
    page_name: Mapped[str] = mapped_column(String(160))
    ad_text: Mapped[str | None] = mapped_column(Text)
    screenshot_path: Mapped[str | None] = mapped_column(String(200))            # path inside the private storage bucket
    link: Mapped[str | None] = mapped_column(String(500))
    price_seen: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    offer_seen: Mapped[str | None] = mapped_column(String(300))
    date_seen: Mapped[dt.date] = mapped_column(Date)


class CreativeItem(TimestampMixin, Base):
    """One piece of ad content (a Meta ad, an Instagram caption or a WhatsApp status) saved on a launch project.

    `content` holds the fields as the seller last edited them; AI text is never used until the seller saves it.
    """

    __tablename__ = "creative_items"
    __table_args__ = (CheckConstraint("kind IN ('meta_ad', 'instagram', 'whatsapp_status')", name="creative_kind_known"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    launch_project_id: Mapped[int] = mapped_column(ForeignKey("launch_projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    content: Mapped[dict] = mapped_column(JSONB)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
