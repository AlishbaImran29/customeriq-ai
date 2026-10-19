from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order


class Customer(TimestampMixin, Base):
    """A store customer, identified by the `customer_id` from imported files."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    # Optional; used only to open a WhatsApp confirmation chat (Order Risk Check).
    phone: Mapped[str | None] = mapped_column(String(40))

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")
