"""Order Risk Check: the extra facts about an order and what happened to it.

All new columns are optional (NULL = "not provided", never zero), so existing orders, files
and dashboards are unchanged:
- ordered_at: the time of day of the order (order_date keeps only the day);
- item_count / distinct_products: how many items and how many different products;
- outcome / outcome_date / label_source: whether the parcel was delivered or returned, when
  that became known, and where the label came from ("proxy: cancellations" or "courier data");
- address_length / has_house_number / phone_valid: simple checks made while importing. The
  address text itself is NOT stored;
- customers.phone: needed for the WhatsApp confirmation link.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("ordered_at", sa.DateTime(), nullable=True))
    op.add_column("orders", sa.Column("item_count", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("distinct_products", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("outcome", sa.String(length=20), nullable=True))
    op.add_column("orders", sa.Column("outcome_date", sa.Date(), nullable=True))
    op.add_column("orders", sa.Column("label_source", sa.String(length=40), nullable=True))
    op.add_column("orders", sa.Column("address_length", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("has_house_number", sa.Boolean(), nullable=True))
    op.add_column("orders", sa.Column("phone_valid", sa.Boolean(), nullable=True))
    op.add_column("customers", sa.Column("phone", sa.String(length=40), nullable=True))
    op.create_check_constraint(
        "order_outcome_known", "orders", "outcome IS NULL OR outcome IN ('delivered', 'returned')"
    )
    op.create_check_constraint(
        "order_label_source_known",
        "orders",
        "label_source IS NULL OR label_source IN ('proxy: cancellations', 'courier data')",
    )
    op.create_check_constraint(
        "order_item_counts_positive",
        "orders",
        "(item_count IS NULL OR item_count >= 1) AND (distinct_products IS NULL OR distinct_products >= 1)",
    )


def downgrade() -> None:
    op.drop_constraint("order_item_counts_positive", "orders", type_="check")
    op.drop_constraint("order_label_source_known", "orders", type_="check")
    op.drop_constraint("order_outcome_known", "orders", type_="check")
    op.drop_column("customers", "phone")
    for column in (
        "phone_valid", "has_house_number", "address_length", "label_source", "outcome_date",
        "outcome", "distinct_products", "item_count", "ordered_at",
    ):
        op.drop_column("orders", column)
