"""Meta Ads: order attribution (campaign), what Meta reports per ad-spend row, and the log of Conversions API purchase events.

Adds optional columns and one new table.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("utm_source", sa.String(length=100), nullable=True))
    op.add_column("orders", sa.Column("utm_campaign", sa.String(length=160), nullable=True))
    op.add_column("ad_spend", sa.Column("meta_purchases", sa.Integer(), nullable=True))
    op.add_column("ad_spend", sa.Column("meta_revenue", sa.Numeric(12, 2), nullable=True))
    op.create_table(
        "meta_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.String(length=200), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_meta_events_order_id_orders", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_meta_events"),
        sa.UniqueConstraint("event_id", name="uq_meta_events_event_id"),
        sa.CheckConstraint("status IN ('pending', 'sent', 'dry_run', 'failed', 'skipped')", name="ck_meta_events_meta_event_status_known"),
    )
    op.create_index("ix_meta_events_order_id", "meta_events", ["order_id"])
    op.create_index("ix_meta_events_status", "meta_events", ["status"])


def downgrade() -> None:
    op.drop_index("ix_meta_events_status", table_name="meta_events")
    op.drop_index("ix_meta_events_order_id", table_name="meta_events")
    op.drop_table("meta_events")
    op.drop_column("ad_spend", "meta_revenue")
    op.drop_column("ad_spend", "meta_purchases")
    op.drop_column("orders", "utm_campaign")
    op.drop_column("orders", "utm_source")
