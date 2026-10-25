"""Support inbox: conversations, internal notes, and the seller's own FAQ answers.

New tables only.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_now = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=8), server_default="open", nullable=False),
        sa.Column("assigned_to", sa.String(length=320), nullable=True),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_conversations_customer_id_customers", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        sa.UniqueConstraint("customer_id", name="uq_conversations_customer"),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_conversations_conversation_status_known"),
    )
    op.create_table(
        "inbox_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(length=320), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_inbox_notes_customer_id_customers", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_inbox_notes"),
    )
    op.create_index("ix_inbox_notes_customer_id", "inbox_notes", ["customer_id"])
    op.create_table(
        "faq_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("keywords", sa.String(length=300), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_faq_entries"),
    )


def downgrade() -> None:
    op.drop_table("faq_entries")
    op.drop_index("ix_inbox_notes_customer_id", table_name="inbox_notes")
    op.drop_table("inbox_notes")
    op.drop_table("conversations")
