"""Auto Messenger, part 5: journeys, who is on them, and the scheduler's bookmarks.

New tables only.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: str | None = "0020"
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
        "journeys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("trigger_segment", sa.String(length=30), nullable=False),
        sa.Column("anchor", sa.String(length=12), server_default="enrollment", nullable=False),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column("loop_every_days", sa.Integer(), nullable=True),
        sa.Column("max_sends", sa.Integer(), nullable=True),
        sa.Column("max_per_30_days", sa.Integer(), nullable=True),
        sa.Column("grace_days", sa.Integer(), server_default="3", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_journeys"),
        sa.UniqueConstraint("key", name="uq_journeys_key"),
        sa.CheckConstraint("anchor IN ('enrollment', 'first_order')", name="ck_journeys_journey_anchor_known"),
    )

    op.create_table(
        "journey_enrollments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("journey_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anchor_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("holdout", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("state", sa.String(length=10), server_default="active", nullable=False),
        sa.Column("stop_reason", sa.String(length=30), nullable=True),
        sa.Column("step_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sends", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_journey_enrollments"),
        sa.ForeignKeyConstraint(["journey_id"], ["journeys.id"], name="fk_journey_enrollments_journey_id_journeys", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_journey_enrollments_customer_id_customers", ondelete="CASCADE"),
        sa.CheckConstraint("state IN ('active', 'completed', 'stopped', 'holdout')", name="ck_journey_enrollments_enrollment_state_known"),
    )
    op.create_index("ix_journey_enrollments_journey_id", "journey_enrollments", ["journey_id"])
    op.create_index("ix_journey_enrollments_customer_id", "journey_enrollments", ["customer_id"])
    op.create_index("ix_journey_enrollments_state", "journey_enrollments", ["state"])
    op.create_index("ix_journey_enrollments_next_run_at", "journey_enrollments", ["next_run_at"])
    op.create_index(
        "uq_journey_enrollments_active", "journey_enrollments", ["journey_id", "customer_id"], unique=True,
        postgresql_where=sa.text("state IN ('active', 'holdout')"),
    )

    op.create_table(
        "scheduler_state",
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("value", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_scheduler_state"),
    )
    for table in ("journeys", "journey_enrollments", "scheduler_state"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("scheduler_state")
    op.drop_table("journey_enrollments")
    op.drop_table("journeys")
