from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ModelReport(TimestampMixin, Base):
    """One line of the Model Report Card: how a model scored against its simple baseline, and whether the trust rule
    shows or hides it. A new line is saved only when something changed, so the table is the history of every decision
    (for example "hidden after the 3 March import, because it no longer beat the baseline")."""

    __tablename__ = "model_reports"
    __table_args__ = (
        CheckConstraint("decision IN ('shown', 'hidden')", name="decision_known"),
        Index("ix_model_reports_model_created", "model", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    model: Mapped[str] = mapped_column(String(40))  # churn | clv | revenue_forecast | order_risk | season:<id>
    label: Mapped[str] = mapped_column(String(80))
    decision: Mapped[str] = mapped_column(String(10))  # "shown" | "hidden"
    reason: Mapped[str | None] = mapped_column(Text)
    metric: Mapped[str | None] = mapped_column(String(30))
    model_score: Mapped[float | None] = mapped_column(Float)
    baseline_score: Mapped[float | None] = mapped_column(Float)
    higher_is_better: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    test_size: Mapped[int | None] = mapped_column(Integer)
    split_date: Mapped[date | None] = mapped_column(Date)
