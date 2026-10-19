"""Social Seller Mode, step 2: what a seller types when adding an order by hand.

All new columns are optional, so existing orders and imports are unchanged:
- payment_type: "cod" (cash on delivery) or "prepaid";
- city: where the order is going;
- products: the product names, joined with ", ";
- note: a free note from the seller.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("payment_type", sa.String(length=10), nullable=True))
    op.add_column("orders", sa.Column("city", sa.String(length=100), nullable=True))
    op.add_column("orders", sa.Column("products", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("note", sa.Text(), nullable=True))
    op.create_check_constraint(
        "order_payment_type_known", "orders", "payment_type IS NULL OR payment_type IN ('cod', 'prepaid')"
    )


def downgrade() -> None:
    op.drop_constraint("order_payment_type_known", "orders", type_="check")
    for column in ("note", "products", "city", "payment_type"):
        op.drop_column("orders", column)
