"""Social Seller Mode, step 3: remember which orders came from a WhatsApp chat.

orders.source is empty for every existing order and for orders from files or the form. It is
"whatsapp_chat" for an order the seller accepted from a chat export, so that all of them can be
deleted together ("Delete all imported WhatsApp data"). No chat text is stored anywhere.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("source", sa.String(length=20), nullable=True))
    op.create_index("ix_orders_source", "orders", ["source"])


def downgrade() -> None:
    op.drop_index("ix_orders_source", table_name="orders")
    op.drop_column("orders", "source")
