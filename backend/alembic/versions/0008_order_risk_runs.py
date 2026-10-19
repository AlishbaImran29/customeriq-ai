"""Order Risk Check: remember each model training run and the decision made.

The new table gets row-level security like every other table (see 0005): hosts such as
Supabase expose public tables through a REST API, and with the security switched on and no
policies that API can read nothing. The app connects as the table owner and is unaffected.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "order_risk_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("label_source", sa.String(length=80), nullable=True),
        sa.Column("metric", sa.String(length=20), nullable=False),
        sa.Column("model_score", sa.Float(), nullable=True),
        sa.Column("baseline_score", sa.Float(), nullable=True),
        sa.Column("top_fraction", sa.Float(), nullable=False),
        sa.Column("model_precision_top", sa.Float(), nullable=True),
        sa.Column("baseline_precision_top", sa.Float(), nullable=True),
        sa.Column("split_date", sa.Date(), nullable=True),
        sa.Column("train_end", sa.Date(), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("maturity_days", sa.Integer(), nullable=False),
        sa.Column("train_rows", sa.Integer(), nullable=False),
        sa.Column("test_rows", sa.Integer(), nullable=False),
        sa.Column("test_return_rate", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_order_risk_runs"),
    )
    op.execute('ALTER TABLE "order_risk_runs" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("order_risk_runs")
