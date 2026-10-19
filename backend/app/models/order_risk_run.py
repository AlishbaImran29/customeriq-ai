import uuid
from datetime import date

from sqlalchemy import Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class OrderRiskRun(TimestampMixin, Base):
    """One training run of the Order Risk model and the decision the trust rule made.

    The scores are saved whether or not the model was good enough, so the app can always show
    why a prediction is, or is not, available."""

    __tablename__ = "order_risk_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    decision: Mapped[str] = mapped_column(String(20))  # "available" | "unavailable"
    reason: Mapped[str | None] = mapped_column(Text)
    label_source: Mapped[str | None] = mapped_column(String(80))
    metric: Mapped[str] = mapped_column(String(20))  # e.g. "ROC-AUC"
    model_score: Mapped[float | None] = mapped_column(Float)
    baseline_score: Mapped[float | None] = mapped_column(Float)
    top_fraction: Mapped[float] = mapped_column(Float)
    model_precision_top: Mapped[float | None] = mapped_column(Float)
    baseline_precision_top: Mapped[float | None] = mapped_column(Float)
    split_date: Mapped[date | None] = mapped_column(Date)  # first day of the test period
    train_end: Mapped[date | None] = mapped_column(Date)
    as_of: Mapped[date | None] = mapped_column(Date)  # the latest order in the data
    maturity_days: Mapped[int] = mapped_column(Integer)
    train_rows: Mapped[int] = mapped_column(Integer, default=0)
    test_rows: Mapped[int] = mapped_column(Integer, default=0)
    test_return_rate: Mapped[float | None] = mapped_column(Float)
