"""Auto Messenger, part 4: products to announce, campaigns and their recipients.

New tables only.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_now = sa.func.now()


def _stamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "catalog_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=14), server_default="manual", nullable=False),
        sa.Column("external_id", sa.String(length=60), nullable=True),
        sa.Column("launch_project_id", sa.Integer(), nullable=True),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_catalog_products"),
        sa.ForeignKeyConstraint(["launch_project_id"], ["launch_projects.id"], name="fk_catalog_products_launch_project_id_launch_projects", ondelete="SET NULL"),
        sa.UniqueConstraint("external_id", name="uq_catalog_products_external_id"),
        sa.CheckConstraint("source IN ('manual', 'shopify', 'launch_studio')", name="ck_catalog_products_catalog_source_known"),
        sa.CheckConstraint("price IS NULL OR price >= 0", name="ck_catalog_products_catalog_price_non_negative"),
    )

    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="draft", nullable=False),
        sa.Column("audience", postgresql.JSONB(), nullable=False),
        sa.Column("offer_text", sa.String(length=300), nullable=True),
        sa.Column("early_access_hours", sa.Integer(), server_default="24", nullable=False),
        sa.Column("messages", postgresql.JSONB(), nullable=True),
        sa.Column("ai_draft", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_campaigns"),
        sa.ForeignKeyConstraint(["product_id"], ["catalog_products.id"], name="fk_campaigns_product_id_catalog_products", ondelete="SET NULL"),
        sa.CheckConstraint("status IN ('draft', 'approved', 'sending', 'completed', 'cancelled')", name="ck_campaigns_campaign_status_known"),
        sa.CheckConstraint("early_access_hours >= 0", name="ck_campaigns_campaign_early_non_negative"),
    )
    op.create_index("ix_campaigns_product_id", "campaigns", ["product_id"])
    op.create_index("ix_campaigns_status", "campaigns", ["status"])

    op.create_table(
        "campaign_recipients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("segment", sa.String(length=30), nullable=False),
        sa.Column("stage", sa.String(length=8), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=8), server_default="pending", nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=100), nullable=True),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_campaign_recipients"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], name="fk_campaign_recipients_campaign_id_campaigns", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_campaign_recipients_customer_id_customers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], name="fk_campaign_recipients_message_id_messages", ondelete="SET NULL"),
        sa.UniqueConstraint("campaign_id", "customer_id", name="uq_campaign_recipients_campaign_customer"),
        sa.CheckConstraint("stage IN ('early', 'regular')", name="ck_campaign_recipients_recipient_stage_known"),
        sa.CheckConstraint("status IN ('pending', 'sent', 'skipped')", name="ck_campaign_recipients_recipient_status_known"),
    )
    op.create_index("ix_campaign_recipients_campaign_id", "campaign_recipients", ["campaign_id"])
    op.create_index("ix_campaign_recipients_customer_id", "campaign_recipients", ["customer_id"])
    op.create_index("ix_campaign_recipients_scheduled_for", "campaign_recipients", ["scheduled_for"])
    op.create_index("ix_campaign_recipients_status", "campaign_recipients", ["status"])

    for table in ("catalog_products", "campaigns", "campaign_recipients"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("campaign_recipients")
    op.drop_table("campaigns")
    op.drop_table("catalog_products")
