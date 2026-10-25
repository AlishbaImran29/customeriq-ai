"""Returns, refunds (recorded by the seller, never executed) and complaint tickets.

New tables only.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_now = sa.func.now()


def _stamps() -> list[sa.Column]:
    return [sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False)]


def upgrade() -> None:
    op.create_table(
        "return_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="requested", nullable=False),
        sa.Column("resolution", sa.String(length=12), nullable=True),
        sa.Column("decision_note", sa.String(length=300), nullable=True),
        sa.Column("restocked", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("replacement_order_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        *_stamps(),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_return_requests_order_id_orders", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_return_requests_customer_id_customers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replacement_order_id"], ["orders.id"], name="fk_return_requests_replacement_order_id_orders", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_return_requests"),
        sa.CheckConstraint("status IN ('requested', 'approved', 'rejected', 'received', 'closed')", name="ck_return_requests_return_status_known"),
        sa.CheckConstraint("resolution IS NULL OR resolution IN ('refund', 'replacement', 'none')", name="ck_return_requests_return_resolution_known"),
    )
    op.create_index("ix_return_requests_order_id", "return_requests", ["order_id"])
    op.create_index("ix_return_requests_customer_id", "return_requests", ["customer_id"])
    op.create_index("ix_return_requests_status", "return_requests", ["status"])
    op.create_table(
        "return_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("return_id", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("mime_type", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["return_id"], ["return_requests.id"], name="fk_return_evidence_return_id_return_requests", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_return_evidence"),
    )
    op.create_index("ix_return_evidence_return_id", "return_evidence", ["return_id"])
    op.create_table(
        "return_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("return_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=30), nullable=False),
        sa.Column("detail", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("by", sa.String(length=320), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["return_id"], ["return_requests.id"], name="fk_return_events_return_id_return_requests", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_return_events"),
    )
    op.create_index("ix_return_events_return_id", "return_events", ["return_id"])
    op.create_table(
        "refunds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("return_id", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="requested", nullable=False),
        sa.Column("method", sa.String(length=60), nullable=True),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_by", sa.String(length=320), nullable=True),
        *_stamps(),
        sa.ForeignKeyConstraint(["return_id"], ["return_requests.id"], name="fk_refunds_return_id_return_requests", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_refunds_order_id_orders", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_refunds"),
        sa.CheckConstraint("status IN ('requested', 'recorded')", name="ck_refunds_refund_status_known"),
        sa.CheckConstraint("amount >= 0", name="ck_refunds_refund_amount_non_negative"),
    )
    op.create_index("ix_refunds_return_id", "refunds", ["return_id"])
    op.create_index("ix_refunds_order_id", "refunds", ["order_id"])
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=12), server_default="open", nullable=False),
        sa.Column("priority", sa.String(length=8), server_default="normal", nullable=False),
        sa.Column("assigned_to", sa.String(length=320), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *_stamps(),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_tickets_customer_id_customers", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_tickets_order_id_orders", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_tickets"),
        sa.CheckConstraint("status IN ('open', 'in_progress', 'resolved', 'closed')", name="ck_tickets_ticket_status_known"),
        sa.CheckConstraint("priority IN ('low', 'normal', 'high')", name="ck_tickets_ticket_priority_known"),
    )
    op.create_index("ix_tickets_customer_id", "tickets", ["customer_id"])
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_table(
        "ticket_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(length=320), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], name="fk_ticket_notes_ticket_id_tickets", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_ticket_notes"),
    )
    op.create_index("ix_ticket_notes_ticket_id", "ticket_notes", ["ticket_id"])


def downgrade() -> None:
    for index, table in (("ix_ticket_notes_ticket_id", "ticket_notes"),):
        op.drop_index(index, table_name=table)
    op.drop_table("ticket_notes")
    op.drop_index("ix_tickets_status", table_name="tickets")
    op.drop_index("ix_tickets_customer_id", table_name="tickets")
    op.drop_table("tickets")
    op.drop_index("ix_refunds_order_id", table_name="refunds")
    op.drop_index("ix_refunds_return_id", table_name="refunds")
    op.drop_table("refunds")
    op.drop_index("ix_return_events_return_id", table_name="return_events")
    op.drop_table("return_events")
    op.drop_index("ix_return_evidence_return_id", table_name="return_evidence")
    op.drop_table("return_evidence")
    op.drop_index("ix_return_requests_status", table_name="return_requests")
    op.drop_index("ix_return_requests_customer_id", table_name="return_requests")
    op.drop_index("ix_return_requests_order_id", table_name="return_requests")
    op.drop_table("return_requests")
