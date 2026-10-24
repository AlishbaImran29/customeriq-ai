import datetime as dt

from sqlalchemy import CheckConstraint, Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ProductSale(TimestampMixin, Base):
    """Units of one product sold in one week (the week starts on a Monday).

    Weekly totals keep the table small and are all the Season Forecast needs. A product with no row
    for a week sold nothing that week (inside the dates the data covers).
    """

    __tablename__ = "product_sales"
    __table_args__ = (
        UniqueConstraint("product", "week_start", name="uq_product_sales_product_week"),
        CheckConstraint("units >= 0", name="units_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product: Mapped[str] = mapped_column(String(120), index=True)
    week_start: Mapped[dt.date] = mapped_column(Date, index=True)
    units: Mapped[int] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(String(30))        # "import", "public: ..." or "demo (synthetic)"
