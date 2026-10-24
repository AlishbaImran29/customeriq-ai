"""Auto Messenger, part 2: order status history, handled webhook calls, a tracking number on shipments and a preferred
language on customers.

Two new tables, and two new OPTIONAL columns (nothing is rewritten or removed).

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "order_status_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("courier", sa.String(length=60), nullable=True),
        sa.Column("tracking_number", sa.String(length=80), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_order_status_history"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_order_status_history_order_id_orders", ondelete="CASCADE"),
        sa.CheckConstraint("status IN ('confirmed', 'dispatched', 'in_transit', 'out_for_delivery', 'delivered', 'returned')", name="ck_order_status_history_order_status_known"),
        sa.CheckConstraint("source IN ('shopify', 'courier_import', 'manual', 'system')", name="ck_order_status_history_order_status_source_known"),
    )
    op.create_index("ix_order_status_history_order_id", "order_status_history", ["order_id"])
    op.create_index("ix_order_status_history_order_at", "order_status_history", ["order_id", "at"])

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("event_id", sa.String(length=120), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_events"),
        sa.UniqueConstraint("source", "event_id", name="uq_webhook_events_source_event"),
    )

    op.add_column("shipments", sa.Column("tracking_number", sa.String(length=80), nullable=True))
    op.add_column("customers", sa.Column("preferred_language", sa.String(length=2), nullable=True))
    for table in ("order_status_history", "webhook_events"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_column("customers", "preferred_language")
    op.drop_column("shipments", "tracking_number")
    op.drop_table("webhook_events")
    op.drop_table("order_status_history")
