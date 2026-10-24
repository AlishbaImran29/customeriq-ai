"""Customer records: tags, notes, acquisition source, status, and the audit trail of merges and deletions.

Adds optional columns to customers (nothing existing changes) and one new table.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("tags", postgresql.JSONB(), server_default="[]", nullable=False))
    op.add_column("customers", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("customers", sa.Column("acquisition_source", sa.String(length=60), nullable=True))
    op.add_column("customers", sa.Column("status", sa.String(length=12), server_default="active", nullable=False))
    op.add_column("customers", sa.Column("anonymised_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_customers_customer_status_known", "customers", "status IN ('active', 'blocked', 'anonymised')")

    op.create_table(
        "customer_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=12), nullable=False),
        sa.Column("customer_ref", sa.String(length=100), nullable=False),
        sa.Column("detail", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_customer_audit"),
        sa.CheckConstraint("action IN ('edit', 'merge', 'anonymise', 'delete')", name="ck_customer_audit_audit_action_known"),
    )
    op.create_index("ix_customer_audit_at", "customer_audit", ["at"])


def downgrade() -> None:
    op.drop_index("ix_customer_audit_at", table_name="customer_audit")
    op.drop_table("customer_audit")
    op.drop_constraint("ck_customers_customer_status_known", "customers", type_="check")
    for column in ("anonymised_at", "status", "acquisition_source", "notes", "tags"):
        op.drop_column("customers", column)
