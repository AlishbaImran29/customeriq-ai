"""Profit analytics: the shop's cost numbers and ad spend.

New tables only.

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_now = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "business_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("packing_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("return_shipping_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_business_settings"),
    )
    op.create_table(
        "ad_spend",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("spend_date", sa.Date(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("campaign", sa.String(length=160), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("source", sa.String(length=20), server_default="manual", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ad_spend"),
        sa.CheckConstraint("amount >= 0", name="ck_ad_spend_ad_spend_non_negative"),
        sa.CheckConstraint("channel IN ('instagram', 'whatsapp', 'facebook', 'website', 'other')", name="ck_ad_spend_ad_spend_channel_known"),
    )
    op.create_index("ix_ad_spend_date_channel", "ad_spend", ["spend_date", "channel"])


def downgrade() -> None:
    op.drop_index("ix_ad_spend_date_channel", table_name="ad_spend")
    op.drop_table("ad_spend")
    op.drop_table("business_settings")
