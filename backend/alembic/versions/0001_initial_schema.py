"""Initial schema: customers, import_jobs, orders.

Revision ID: 0001
Revises:
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

import_status = postgresql.ENUM(
    "pending", "processing", "completed", "failed", name="import_status", create_type=False
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    import_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_customers"),
    )
    op.create_index("ix_customers_external_id", "customers", ["external_id"], unique=True)
    op.create_index("ix_customers_email", "customers", ["email"])

    op.create_table(
        "import_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=10), nullable=False),
        sa.Column("status", import_status, nullable=False),
        sa.Column("rows_received", sa.Integer(), nullable=False),
        sa.Column("rows_imported", sa.Integer(), nullable=False),
        sa.Column("rows_rejected", sa.Integer(), nullable=False),
        sa.Column("errors", postgresql.JSONB(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_import_jobs"),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("order_value", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("product_category", sa.String(length=100), nullable=True),
        sa.Column("channel", sa.String(length=50), nullable=True),
        sa.Column("engagement_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("import_job_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_orders"),
        sa.CheckConstraint("order_value >= 0", name="ck_orders_order_value_non_negative"),
        sa.CheckConstraint(
            "engagement_score IS NULL OR (engagement_score >= 0 AND engagement_score <= 100)",
            name="ck_orders_engagement_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"],
            name="fk_orders_customer_id_customers", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["import_job_id"], ["import_jobs.id"],
            name="fk_orders_import_job_id_import_jobs", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_orders_external_id", "orders", ["external_id"], unique=True)
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_order_date", "orders", ["order_date"])
    op.create_index("ix_orders_import_job_id", "orders", ["import_job_id"])


def downgrade() -> None:
    op.drop_table("orders")
    op.drop_table("import_jobs")
    op.drop_table("customers")
    import_status.drop(op.get_bind(), checkfirst=True)
