"""Abandoned carts (Shopify checkouts) and the two reminder delays in the messaging settings.

New table, and two optional columns on messaging_settings.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_now = sa.func.now()


def upgrade() -> None:
    op.add_column("messaging_settings", sa.Column("cart_first_minutes", sa.Integer(), server_default="60", nullable=False))
    op.add_column("messaging_settings", sa.Column("cart_second_hours", sa.Integer(), server_default="24", nullable=False))   # 0 = no second reminder
    op.create_table(
        "abandoned_carts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("checkout_id", sa.String(length=60), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("items", sa.Text(), nullable=True),
        sa.Column("total", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("checkout_url", sa.String(length=600), nullable=True),
        sa.Column("checkout_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="open", nullable=False),
        sa.Column("reminders_sent", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_abandoned_carts_customer_id_customers", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_abandoned_carts"),
        sa.UniqueConstraint("checkout_id", name="uq_abandoned_carts_checkout_id"),
        sa.CheckConstraint("status IN ('open', 'recovered', 'expired', 'no_contact')", name="ck_abandoned_carts_cart_status_known"),
    )
    op.create_index("ix_abandoned_carts_customer_id", "abandoned_carts", ["customer_id"])
    op.create_index("ix_abandoned_carts_status_updated", "abandoned_carts", ["status", "checkout_updated_at"])


def downgrade() -> None:
    op.drop_index("ix_abandoned_carts_status_updated", table_name="abandoned_carts")
    op.drop_index("ix_abandoned_carts_customer_id", table_name="abandoned_carts")
    op.drop_table("abandoned_carts")
    op.drop_column("messaging_settings", "cart_second_hours")
    op.drop_column("messaging_settings", "cart_first_minutes")
