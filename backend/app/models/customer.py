from typing import TYPE_CHECKING

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order


class Customer(TimestampMixin, Base):
    """A store customer, identified by the `customer_id` from imported files."""

    __tablename__ = "customers"
    __table_args__ = (
        # One customer per phone number: this is what merges repeat customers (see services/phone.py).
        Index(
            "uq_customers_phone_normalised", "phone_normalised", unique=True,
            postgresql_where=text("phone_normalised IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    # Optional: a seller on WhatsApp or Instagram knows a phone number, not an email address.
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    # Optional; used only to open a WhatsApp confirmation chat (Order Risk Check).
    phone: Mapped[str | None] = mapped_column(String(40))
    # The Pakistani mobile number as +923XXXXXXXXX (None if there is none, or it is not one).
    phone_normalised: Mapped[str | None] = mapped_column(String(13))
    # The language this customer likes to be messaged in ("ur" or "en"); None = the seller's default (Auto Messenger).
    preferred_language: Mapped[str | None] = mapped_column(String(2))

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")
