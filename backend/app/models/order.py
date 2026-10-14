import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.customer import Customer


class Order(TimestampMixin, Base):
    """One order row, as imported (one row per order in CSV/Excel files)."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("order_value >= 0", name="order_value_non_negative"),
        CheckConstraint(
            "engagement_score IS NULL OR (engagement_score >= 0 AND engagement_score <= 100)",
            name="engagement_score_range",
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
    import_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_jobs.id", ondelete="SET NULL"), index=True
    )

    customer: Mapped["Customer"] = relationship(back_populates="orders")
