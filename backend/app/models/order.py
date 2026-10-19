import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.customer import Customer


# What happened to a parcel, and where that label came from (Order Risk Check).
OUTCOME_DELIVERED = "delivered"
OUTCOME_RETURNED = "returned"
OUTCOMES = (OUTCOME_DELIVERED, OUTCOME_RETURNED)
# "proxy": the order was later cancelled (a credit note, as in Online Retail II).
# "courier": a courier status file said the parcel came back.
LABEL_PROXY = "proxy: cancellations"
LABEL_COURIER = "courier data"
LABEL_SOURCES = (LABEL_PROXY, LABEL_COURIER)


class Order(TimestampMixin, Base):
    """One order row, as imported (one row per order in CSV/Excel files)."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("order_value >= 0", name="order_value_non_negative"),
        CheckConstraint(
            "engagement_score IS NULL OR (engagement_score >= 0 AND engagement_score <= 100)",
            name="engagement_score_range",
        ),
        CheckConstraint("outcome IS NULL OR outcome IN ('delivered', 'returned')", name="order_outcome_known"),
        CheckConstraint(
            "label_source IS NULL OR label_source IN ('proxy: cancellations', 'courier data')",
            name="order_label_source_known",
        ),
        CheckConstraint(
            "(item_count IS NULL OR item_count >= 1) AND (distinct_products IS NULL OR distinct_products >= 1)",
            name="order_item_counts_positive",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    order_date: Mapped[date] = mapped_column(Date, index=True)
    order_value: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    product_category: Mapped[str | None] = mapped_column(String(100))
    channel: Mapped[str | None] = mapped_column(String(50))
    # Optional 0–100 engagement score from the import. NULL means "not provided";
    # it is never treated as zero by the health score.
    engagement_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # Order Risk Check facts. All optional: NULL means "not provided", never zero.
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime)  # time of day; order_date is the day
    item_count: Mapped[int | None] = mapped_column(Integer)
    distinct_products: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(String(20))  # "delivered" | "returned"
    outcome_date: Mapped[date | None] = mapped_column(Date)  # the day the outcome became known
    label_source: Mapped[str | None] = mapped_column(String(40))
    # Checks made while importing. The address text itself is never stored.
    address_length: Mapped[int | None] = mapped_column(Integer)
    has_house_number: Mapped[bool | None] = mapped_column(Boolean)
    phone_valid: Mapped[bool | None] = mapped_column(Boolean)
    import_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_jobs.id", ondelete="SET NULL"), index=True
    )

    customer: Mapped["Customer"] = relationship(back_populates="orders")
