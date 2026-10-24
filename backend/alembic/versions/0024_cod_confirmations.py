"""COD auto-confirmation: one row per cash-on-delivery order that was asked to confirm.

New table only.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_now = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "cod_confirmations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=12), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=10), nullable=True),
        sa.Column("reply_text", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_cod_confirmations_order_id_orders", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_cod_confirmations"),
        sa.UniqueConstraint("order_id", name="uq_cod_confirmations_order"),
        sa.CheckConstraint("state IN ('awaiting', 'confirmed', 'cancelled', 'needs_call')", name="ck_cod_confirmations_cod_state_known"),
        sa.CheckConstraint("resolved_by IS NULL OR resolved_by IN ('customer', 'seller')", name="ck_cod_confirmations_cod_resolved_by_known"),
    )
    op.create_index("ix_cod_confirmations_state_deadline", "cod_confirmations", ["state", "deadline_at"])


def downgrade() -> None:
    op.drop_index("ix_cod_confirmations_state_deadline", table_name="cod_confirmations")
    op.drop_table("cod_confirmations")
