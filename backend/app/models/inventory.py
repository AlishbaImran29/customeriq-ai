"""Simple inventory: stock items and an auditable list of every change to them."""

import datetime as dt
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

MOVEMENT_KINDS = ("receive", "adjustment", "reserve", "release", "sale", "return")


class StockItem(TimestampMixin, Base):
    """One thing the seller sells and counts. `stock` is what is on the shelf; `reserved` is promised to confirmed orders
    that have not left yet. What can still be promised is stock - reserved."""

    __tablename__ = "stock_items"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_stock_items_sku"),
        CheckConstraint("reserved >= 0", name="stock_reserved_non_negative"),
        CheckConstraint("reorder_threshold >= 0", name="stock_threshold_non_negative"),
        CheckConstraint("status IN ('active', 'archived')", name="stock_status_known"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str | None] = mapped_column(String(100))
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    selling_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    stock: Mapped[int] = mapped_column(Integer, default=0, server_default="0")      # may go below 0: that means oversold
    reserved: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reorder_threshold: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    supplier: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(10), default="active", server_default="active")


class StockMovement(Base):
    """One change to one item. Rows are only ever added. `idempotency_key` is unique, so the same order event can never
    change the stock twice (a retried webhook, a courier file imported again)."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_stock_movements_key"),
        CheckConstraint("kind IN ('receive', 'adjustment', 'reserve', 'release', 'sale', 'return')", name="movement_kind_known"),
        Index("ix_stock_movements_item_at", "item_id", "at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("stock_items.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(12))
    quantity: Mapped[int] = mapped_column(Integer)         # always positive: how many units this was about
    stock_delta: Mapped[int] = mapped_column(Integer)      # the change to stock (negative for a sale)
    reserved_delta: Mapped[int] = mapped_column(Integer)   # the change to reserved
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
