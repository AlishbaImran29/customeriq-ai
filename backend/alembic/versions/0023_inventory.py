"""Simple inventory: stock items and their movements.

New tables only.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_now = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "stock_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("cost_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("selling_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("stock", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reserved", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reorder_threshold", sa.Integer(), server_default="0", nullable=False),
        sa.Column("supplier", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_stock_items"),
        sa.UniqueConstraint("sku", name="uq_stock_items_sku"),
        sa.CheckConstraint("reserved >= 0", name="ck_stock_items_stock_reserved_non_negative"),
        sa.CheckConstraint("reorder_threshold >= 0", name="ck_stock_items_stock_threshold_non_negative"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_stock_items_stock_status_known"),
    )
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("stock_delta", sa.Integer(), nullable=False),
        sa.Column("reserved_delta", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=80), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["stock_items.id"], name="fk_stock_movements_item_id_stock_items", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_stock_movements_order_id_orders", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_stock_movements"),
        sa.UniqueConstraint("idempotency_key", name="uq_stock_movements_key"),
        sa.CheckConstraint("kind IN ('receive', 'adjustment', 'reserve', 'release', 'sale', 'return')", name="ck_stock_movements_movement_kind_known"),
    )
    op.create_index("ix_stock_movements_item_at", "stock_movements", ["item_id", "at"])
    op.create_index("ix_stock_movements_order_id", "stock_movements", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_movements_order_id", table_name="stock_movements")
    op.drop_index("ix_stock_movements_item_at", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_table("stock_items")
