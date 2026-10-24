"""Model Report Card: the history of every model's score, baseline and Shown/Hidden decision.

New table only.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_now = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "model_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("decision", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metric", sa.String(length=30), nullable=True),
        sa.Column("model_score", sa.Float(), nullable=True),
        sa.Column("baseline_score", sa.Float(), nullable=True),
        sa.Column("higher_is_better", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("test_size", sa.Integer(), nullable=True),
        sa.Column("split_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_model_reports"),
        sa.CheckConstraint("decision IN ('shown', 'hidden')", name="ck_model_reports_decision_known"),
    )
    op.create_index("ix_model_reports_model_created", "model_reports", ["model", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_model_reports_model_created", table_name="model_reports")
    op.drop_table("model_reports")
