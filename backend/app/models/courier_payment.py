import datetime as dt
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CourierPayment(TimestampMixin, Base):
    """One payment a courier made to the seller: the COD money collected from customers, handed over.

    Which delivered parcels a payment covers is worked out by services/cash_matching.py (oldest first),
    unless `order_refs` names the orders it was for. Nothing is stored per parcel, so the answer can
    never go out of date when payments or shipments change.
    """

    __tablename__ = "courier_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="payment_amount_positive"),
        Index("ix_courier_payments_courier_date", "courier", "payment_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)   # fingerprint: same row, same id
    courier: Mapped[str] = mapped_column(String(60), index=True)                    # the standard name
    payment_date: Mapped[dt.date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reference: Mapped[str | None] = mapped_column(String(100))                      # cheque / transfer number
    order_refs: Mapped[str | None] = mapped_column(Text)                            # order ids it was for, comma separated
    source: Mapped[str | None] = mapped_column(String(30))                          # "import", "manual" or "demo (synthetic)"
