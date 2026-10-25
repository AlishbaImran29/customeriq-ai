"""Leads: the simple pipeline from "showed interest" to "became a customer".

New tables only.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_now = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("phone_normalised", sa.String(length=13), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("campaign", sa.String(length=160), nullable=True),
        sa.Column("utm_source", sa.String(length=100), nullable=True),
        sa.Column("utm_medium", sa.String(length=100), nullable=True),
        sa.Column("utm_campaign", sa.String(length=160), nullable=True),
        sa.Column("product_interest", sa.String(length=200), nullable=True),
        sa.Column("stage", sa.String(length=12), server_default="new", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("lost_reason", sa.String(length=200), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("external_ref", sa.String(length=100), nullable=True),
        sa.Column("follow_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_alerted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_leads_customer_id_customers", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_leads"),
        sa.CheckConstraint("stage IN ('new', 'contacted', 'interested', 'converted', 'lost')", name="ck_leads_lead_stage_known"),
        sa.CheckConstraint("source IN ('manual', 'website_form', 'meta_lead_ad', 'click_to_whatsapp')", name="ck_leads_lead_source_known"),
        sa.CheckConstraint("phone_normalised IS NOT NULL OR email IS NOT NULL", name="ck_leads_lead_has_contact"),
    )
    op.create_index("ix_leads_phone_normalised", "leads", ["phone_normalised"])
    op.create_index("ix_leads_customer_id", "leads", ["customer_id"])
    op.create_index("ix_leads_stage_created", "leads", ["stage", "created_at"])
    op.create_index("uq_leads_external_ref", "leads", ["external_ref"], unique=True, postgresql_where=sa.text("external_ref IS NOT NULL"))
    op.create_table(
        "lead_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=30), nullable=False),
        sa.Column("detail", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], name="fk_lead_events_lead_id_leads", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_lead_events"),
    )
    op.create_index("ix_lead_events_lead_id", "lead_events", ["lead_id"])


def downgrade() -> None:
    op.drop_index("ix_lead_events_lead_id", table_name="lead_events")
    op.drop_table("lead_events")
    op.drop_index("uq_leads_external_ref", table_name="leads")
    op.drop_index("ix_leads_stage_created", table_name="leads")
    op.drop_index("ix_leads_customer_id", table_name="leads")
    op.drop_index("ix_leads_phone_normalised", table_name="leads")
    op.drop_table("leads")
