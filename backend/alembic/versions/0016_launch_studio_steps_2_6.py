"""Launch Studio, steps 2-6: vendors and quotes, competitor ads, creative items, linked products, profit inputs.

New tables, plus two new optional columns on launch_projects. Nothing that exists is changed.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
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
        "vendors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("whatsapp_phone", sa.String(length=13), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("categories", sa.String(length=300), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_vendors"),
    )
    # launch_projects gets its two new columns only after vendors exists.
    op.add_column("launch_projects", sa.Column("chosen_vendor_id", sa.Integer(), nullable=True))
    op.add_column("launch_projects", sa.Column("profit_inputs", postgresql.JSONB(), nullable=True))
    op.create_foreign_key("fk_launch_projects_chosen_vendor_id_vendors", "launch_projects", "vendors", ["chosen_vendor_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "vendor_quotes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=False),
        sa.Column("launch_project_id", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("moq", sa.Integer(), nullable=True),
        sa.Column("delivery_days", sa.Integer(), nullable=True),
        sa.Column("quality_notes", sa.Text(), nullable=True),
        sa.Column("sample_received", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("quoted_on", sa.Date(), nullable=False),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_vendor_quotes"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], name="fk_vendor_quotes_vendor_id_vendors", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["launch_project_id"], ["launch_projects.id"], name="fk_vendor_quotes_launch_project_id_launch_projects", ondelete="CASCADE"),
        sa.CheckConstraint("unit_price >= 0", name="ck_vendor_quotes_quote_price_non_negative"),
        sa.CheckConstraint("moq IS NULL OR moq >= 1", name="ck_vendor_quotes_quote_moq_positive"),
        sa.CheckConstraint("delivery_days IS NULL OR delivery_days >= 0", name="ck_vendor_quotes_quote_days_non_negative"),
    )
    op.create_index("ix_vendor_quotes_vendor_id", "vendor_quotes", ["vendor_id"])
    op.create_index("ix_vendor_quotes_launch_project_id", "vendor_quotes", ["launch_project_id"])

    op.create_table(
        "competitor_ads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("launch_project_id", sa.Integer(), nullable=False),
        sa.Column("page_name", sa.String(length=160), nullable=False),
        sa.Column("ad_text", sa.Text(), nullable=True),
        sa.Column("screenshot_path", sa.String(length=200), nullable=True),
        sa.Column("link", sa.String(length=500), nullable=True),
        sa.Column("price_seen", sa.Numeric(12, 2), nullable=True),
        sa.Column("offer_seen", sa.String(length=300), nullable=True),
        sa.Column("date_seen", sa.Date(), nullable=False),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_competitor_ads"),
        sa.ForeignKeyConstraint(["launch_project_id"], ["launch_projects.id"], name="fk_competitor_ads_launch_project_id_launch_projects", ondelete="CASCADE"),
    )
    op.create_index("ix_competitor_ads_launch_project_id", "competitor_ads", ["launch_project_id"])

    op.create_table(
        "creative_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("launch_project_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("ai_generated", sa.Boolean(), server_default="true", nullable=False),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_creative_items"),
        sa.ForeignKeyConstraint(["launch_project_id"], ["launch_projects.id"], name="fk_creative_items_launch_project_id_launch_projects", ondelete="CASCADE"),
        sa.CheckConstraint("kind IN ('meta_ad', 'instagram', 'whatsapp_status')", name="ck_creative_items_creative_kind_known"),
    )
    op.create_index("ix_creative_items_launch_project_id", "creative_items", ["launch_project_id"])

    op.create_table(
        "launch_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("launch_project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("name_key", sa.String(length=120), nullable=False),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_launch_products"),
        sa.ForeignKeyConstraint(["launch_project_id"], ["launch_projects.id"], name="fk_launch_products_launch_project_id_launch_projects", ondelete="CASCADE"),
        sa.UniqueConstraint("launch_project_id", "name_key", name="uq_launch_products_project_product"),
    )
    op.create_index("ix_launch_products_launch_project_id", "launch_products", ["launch_project_id"])

    # Same protection as every other table (see 0005).
    for table in ("vendors", "vendor_quotes", "competitor_ads", "creative_items", "launch_products"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("launch_products")
    op.drop_table("creative_items")
    op.drop_table("competitor_ads")
    op.drop_table("vendor_quotes")
    op.drop_constraint("fk_launch_projects_chosen_vendor_id_vendors", "launch_projects", type_="foreignkey")
    op.drop_column("launch_projects", "profit_inputs")
    op.drop_column("launch_projects", "chosen_vendor_id")
    op.drop_table("vendors")
