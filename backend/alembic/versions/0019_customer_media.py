"""Auto Messenger, part 3: customer videos and photos received on WhatsApp.

A new table only. The files are kept in a private storage bucket, not in the database.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_now = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "customer_media",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("incoming_message_id", sa.Integer(), nullable=True),
        sa.Column("media_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("mime_type", sa.String(length=80), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("error", sa.String(length=200), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("question_sent", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("share_answer", sa.String(length=7), server_default="pending", nullable=False),
        sa.Column("usable_in_ads", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("usable_marked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_customer_media"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_customer_media_customer_id_customers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_customer_media_order_id_orders", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["incoming_message_id"], ["incoming_messages.id"], name="fk_customer_media_incoming_message_id_incoming_messages", ondelete="SET NULL"),
        sa.UniqueConstraint("incoming_message_id", name="uq_customer_media_incoming_message_id"),
        sa.CheckConstraint("status IN ('pending', 'stored', 'rejected', 'failed')", name="ck_customer_media_media_status_known"),
        sa.CheckConstraint("share_answer IN ('pending', 'yes', 'no')", name="ck_customer_media_media_answer_known"),
        sa.CheckConstraint("kind IN ('image', 'video')", name="ck_customer_media_media_kind_known"),
        sa.CheckConstraint("NOT usable_in_ads OR share_answer = 'yes'", name="ck_customer_media_media_usable_needs_yes"),
    )
    op.create_index("ix_customer_media_customer_id", "customer_media", ["customer_id"])
    op.create_index("ix_customer_media_order_id", "customer_media", ["order_id"])
    op.create_index("ix_customer_media_status", "customer_media", ["status"])
    op.execute('ALTER TABLE "customer_media" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("customer_media")
