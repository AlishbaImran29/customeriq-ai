"""Launch Studio tables: a product idea being taken to market, the Google Trends files uploaded for it,
and a small cache so the same AI question is never paid for twice."""

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, Text
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
