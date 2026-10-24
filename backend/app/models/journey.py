"""Auto Messenger part 5: journeys (automatic follow-ups by customer segment) and who is on them."""

import datetime as dt

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Journey(TimestampMixin, Base):
    """A series of messages for the customers of one segment: trigger -> wait -> message -> ... -> stop.

    `steps` is a list of {"day": N, "event": "journey_at_risk_1"}: send the template of that event N days after the
    start. The start is when the customer joined the journey ("enrollment") or the day of their first order
    ("first_order"). Every journey is created DISABLED: the seller reads it and turns it on.
    """

    __tablename__ = "journeys"
    __table_args__ = (CheckConstraint("anchor IN ('enrollment', 'first_order')", name="journey_anchor_known"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(300))
    trigger_segment: Mapped[str] = mapped_column(String(30))                # "At-Risk Customers"...
    anchor: Mapped[str] = mapped_column(String(12), default="enrollment", server_default="enrollment")
    steps: Mapped[list] = mapped_column(JSONB)
    loop_every_days: Mapped[int | None] = mapped_column(Integer)           # after the last step, start again this many days later
    max_sends: Mapped[int | None] = mapped_column(Integer)                  # at most this many messages per customer, in total
    max_per_30_days: Mapped[int | None] = mapped_column(Integer)           # and at most this many in any 30 days
    grace_days: Mapped[int] = mapped_column(Integer, default=3, server_default="3")    # a step later than this past its day is skipped
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class JourneyEnrollment(TimestampMixin, Base):
    """One customer on one journey. A HOLDOUT customer (a random 10%) is enrolled but never messaged: they are the
    control group that shows what happens when nothing is sent."""

    __tablename__ = "journey_enrollments"
    __table_args__ = (
        CheckConstraint("state IN ('active', 'completed', 'stopped', 'holdout')", name="enrollment_state_known"),
        # A customer can be ACTIVE on a journey only once at a time (they may join again later, after they left).
        Index("uq_journey_enrollments_active", "journey_id", "customer_id", unique=True, postgresql_where=text("state IN ('active', 'holdout')")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    journey_id: Mapped[int] = mapped_column(ForeignKey("journeys.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    enrolled_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    anchor_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))             # when the first message is (or would be) due
    holdout: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    state: Mapped[str] = mapped_column(String(10), default="active", server_default="active", index=True)
    stop_reason: Mapped[str | None] = mapped_column(String(30))             # ordered_again, replied, opted_out, segment_changed
    step_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_run_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sends: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class SchedulerState(Base):
    """Small bookmarks for the scheduler, such as the day the daily segment refresh last ran."""

    __tablename__ = "scheduler_state"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(String(100))
