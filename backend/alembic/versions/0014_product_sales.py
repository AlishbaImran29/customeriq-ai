"""Season Forecast, step C1: units sold per product per week.

A new table, so nothing that exists changes.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_sales",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product", sa.String(length=120), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_product_sales"),
        sa.UniqueConstraint("product", "week_start", name="uq_product_sales_product_week"),
        sa.CheckConstraint("units >= 0", name="ck_product_sales_units_non_negative"),
    )
    op.create_index("ix_product_sales_product", "product_sales", ["product"])
    op.create_index("ix_product_sales_week_start", "product_sales", ["week_start"])
    # Same protection as every other table (see 0005).
    op.execute('ALTER TABLE "product_sales" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("product_sales")
