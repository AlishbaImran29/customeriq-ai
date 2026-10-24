"""Auto Messenger, part 1: consent, message templates, messages, incoming messages and messaging settings.

New tables only, so nothing that exists changes.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-28
"""

import datetime as dt
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
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
        "customer_consent",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("opted_in", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("changed_on", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_customer_consent"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_customer_consent_customer_id_customers", ondelete="CASCADE"),
        sa.UniqueConstraint("customer_id", "channel", name="uq_customer_consent_customer_channel"),
        sa.CheckConstraint("channel IN ('whatsapp', 'email')", name="ck_customer_consent_consent_channel_known"),
    )
    op.create_index("ix_customer_consent_customer_id", "customer_consent", ["customer_id"])

    op.create_table(
        "consent_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_consent_events"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_consent_events_customer_id_customers", ondelete="CASCADE"),
        sa.CheckConstraint("action IN ('opt_in', 'opt_out')", name="ck_consent_events_consent_action_known"),
    )
    op.create_index("ix_consent_events_customer_id", "consent_events", ["customer_id"])
    op.create_index("ix_consent_events_at", "consent_events", ["at"])

    op.create_table(
        "message_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("category", sa.String(length=10), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("event", sa.String(length=40), nullable=True),
        sa.Column("subject", sa.String(length=200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("meta_template_name", sa.String(length=100), nullable=True),
        sa.Column("meta_approval_status", sa.String(length=14), server_default="not_submitted", nullable=False),
        sa.Column("approved_by_seller", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_message_templates"),
        sa.UniqueConstraint("name", "channel", "language", name="uq_message_templates_name_channel_language"),
        sa.CheckConstraint("channel IN ('whatsapp', 'email')", name="ck_message_templates_template_channel_known"),
        sa.CheckConstraint("category IN ('utility', 'marketing')", name="ck_message_templates_template_category_known"),
        sa.CheckConstraint("language IN ('ur', 'en')", name="ck_message_templates_template_language_known"),
        sa.CheckConstraint("meta_approval_status IN ('not_submitted', 'pending', 'approved', 'rejected')", name="ck_message_templates_template_meta_status_known"),
    )
    op.create_index("ix_message_templates_event", "message_templates", ["event"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=10), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=True),
        sa.Column("rendered_text", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="queued", nullable=False),
        sa.Column("error", sa.String(length=200), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("provider_message_id", sa.String(length=128), nullable=True),
        sa.Column("campaign_id", sa.Integer(), nullable=True),
        sa.Column("journey_id", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("dry_run", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_messages_customer_id_customers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["message_templates.id"], name="fk_messages_template_id_message_templates", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_messages_order_id_orders", ondelete="SET NULL"),
        sa.UniqueConstraint("idempotency_key", name="uq_messages_idempotency_key"),
        sa.CheckConstraint("status IN ('queued', 'sent', 'delivered', 'read', 'failed', 'replied', 'skipped')", name="ck_messages_message_status_known"),
        sa.CheckConstraint("channel IN ('whatsapp', 'email')", name="ck_messages_message_channel_known"),
        sa.CheckConstraint("category IN ('utility', 'marketing')", name="ck_messages_message_category_known"),
    )
    for column in ("customer_id", "template_id", "status", "next_attempt_at", "provider_message_id", "campaign_id", "journey_id", "order_id"):
        op.create_index(f"ix_messages_{column}", "messages", [column])

    op.create_table(
        "incoming_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("channel", sa.String(length=10), server_default="whatsapp", nullable=False),
        sa.Column("from_address", sa.String(length=40), nullable=False),
        sa.Column("provider_message_id", sa.String(length=128), nullable=False),
        sa.Column("message_type", sa.String(length=20), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("media_id", sa.String(length=128), nullable=True),
        sa.Column("mime_type", sa.String(length=80), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("is_stop", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("answer", sa.String(length=3), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_incoming_messages"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_incoming_messages_customer_id_customers", ondelete="SET NULL"),
        sa.UniqueConstraint("provider_message_id", name="uq_incoming_messages_provider_message_id"),
    )
    op.create_index("ix_incoming_messages_customer_id", "incoming_messages", ["customer_id"])
    op.create_index("ix_incoming_messages_received_at", "incoming_messages", ["received_at"])

    op.create_table(
        "messaging_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("quiet_start", sa.Time(), nullable=False),
        sa.Column("quiet_end", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(length=40), server_default="Asia/Karachi", nullable=False),
        sa.Column("weekly_marketing_cap", sa.Integer(), server_default="2", nullable=False),
        sa.Column("default_language", sa.String(length=2), server_default="en", nullable=False),
        sa.Column("store_name", sa.String(length=80), nullable=True),
        sa.Column("review_url", sa.String(length=300), nullable=True),
        sa.Column("cost_utility", sa.Numeric(10, 4), nullable=True),
        sa.Column("cost_marketing", sa.Numeric(10, 4), nullable=True),
        sa.Column("campaign_batch_size", sa.Integer(), server_default="30", nullable=False),
        sa.Column("early_access_hours", sa.Integer(), server_default="24", nullable=False),
        sa.Column("holdout_percent", sa.Integer(), server_default="10", nullable=False),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_messaging_settings"),
    )
    # The single settings row, created with safe defaults (dry run ON).
    op.bulk_insert(
        sa.table(
            "messaging_settings", sa.column("id", sa.Integer), sa.column("quiet_start", sa.Time), sa.column("quiet_end", sa.Time),
        ),
        [{"id": 1, "quiet_start": dt.time(21, 0), "quiet_end": dt.time(10, 0)}],
    )

    # Same protection as every other table (see 0005).
    for table in ("customer_consent", "consent_events", "message_templates", "messages", "incoming_messages", "messaging_settings"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    for table in ("messaging_settings", "incoming_messages", "messages", "message_templates", "consent_events", "customer_consent"):
        op.drop_table(table)
