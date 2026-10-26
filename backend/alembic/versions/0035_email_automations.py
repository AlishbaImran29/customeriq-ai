"""Email Automations: email look settings, COD email answers, email log, announcement drafts, customer lifecycle, product image/link.

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("customers", sa.Column("lifecycle", sa.String(length=10), nullable=True))
    op.add_column("catalog_products", sa.Column("image_url", sa.String(length=500), nullable=True))
    op.add_column("catalog_products", sa.Column("product_url", sa.String(length=500), nullable=True))
    op.create_table(
        "email_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("store_name", sa.String(length=80), nullable=True),
        sa.Column("logo_url", sa.String(length=400), nullable=True),
        sa.Column("brand_color", sa.String(length=7), nullable=True),
        sa.Column("support_email", sa.String(length=320), nullable=True),
        sa.Column("store_url", sa.String(length=300), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_email_settings"),
    )
    op.create_table(
        "cod_emails",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_cod_emails_order_id_orders", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_cod_emails"),
        sa.UniqueConstraint("order_id", name="uq_cod_emails_order"),
        sa.CheckConstraint("status IN ('pending', 'confirmed', 'cancelled')", name="ck_cod_emails_cod_email_status_known"),
    )
    op.create_table(
        "email_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("to_email", sa.String(length=320), nullable=False),
        sa.Column("kind", sa.String(length=14), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("error", sa.String(length=200), nullable=True),
        sa.Column("ref_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_email_log_customer_id_customers", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_email_log"),
        sa.CheckConstraint("kind IN ('cod', 'cod_reminder', 'winback', 'new_product', 'test')", name="ck_email_log_email_log_kind_known"),
        sa.CheckConstraint("status IN ('sent', 'mock', 'failed')", name="ck_email_log_email_log_status_known"),
    )
    op.create_index("ix_email_log_created_at", "email_log", ["created_at"])
    op.create_index("ix_email_log_customer_kind", "email_log", ["customer_id", "kind", "created_at"])
    op.create_table(
        "email_announcements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=6), server_default="draft", nullable=False),
        sa.Column("sent_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["product_id"], ["catalog_products.id"], name="fk_email_announcements_product_id_catalog_products", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_email_announcements"),
        sa.CheckConstraint("status IN ('draft', 'sent')", name="ck_email_announcements_email_announcement_status_known"),
    )
    op.create_index("ix_email_announcements_product_id", "email_announcements", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_email_announcements_product_id", table_name="email_announcements")
    op.drop_table("email_announcements")
    op.drop_index("ix_email_log_customer_kind", table_name="email_log")
    op.drop_index("ix_email_log_created_at", table_name="email_log")
    op.drop_table("email_log")
    op.drop_table("cod_emails")
    op.drop_table("email_settings")
    op.drop_column("catalog_products", "product_url")
    op.drop_column("catalog_products", "image_url")
    op.drop_column("customers", "lifecycle")
