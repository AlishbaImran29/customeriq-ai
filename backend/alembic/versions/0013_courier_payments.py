"""Cash Tracker, step B1: the payments couriers make for the COD money they collected.

A new table, so nothing that exists changes. Which parcels each payment covers is calculated, not stored.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "courier_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=40), nullable=False),
        sa.Column("courier", sa.String(length=60), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("order_refs", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_courier_payments"),
        sa.CheckConstraint("amount > 0", name="ck_courier_payments_payment_amount_positive"),
    )
    op.create_index("ix_courier_payments_external_id", "courier_payments", ["external_id"], unique=True)
    op.create_index("ix_courier_payments_courier", "courier_payments", ["courier"])
    op.create_index("ix_courier_payments_payment_date", "courier_payments", ["payment_date"])
    op.create_index("ix_courier_payments_courier_date", "courier_payments", ["courier", "payment_date"])
    # Same protection as every other table (see 0005).
    op.execute('ALTER TABLE "courier_payments" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("courier_payments")
