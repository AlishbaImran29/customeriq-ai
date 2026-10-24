"""Automation engine: workflows, runs, the durable jobs queue, and tasks.

New tables only.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_now = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("trigger", sa.String(length=30), nullable=False),
        sa.Column("trigger_config", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("conditions", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("actions", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_workflows"),
    )
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workflow_id", sa.Integer(), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(length=160), nullable=False),
        sa.Column("context", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("chain", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("status", sa.String(length=10), server_default="running", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], name="fk_workflow_runs_workflow_id_workflows", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runs"),
        sa.UniqueConstraint("workflow_id", "event_key", name="uq_workflow_runs_workflow_event"),
        sa.CheckConstraint("status IN ('running', 'done', 'failed', 'cancelled')", name="ck_workflow_runs_run_status_known"),
    )
    op.create_index("ix_workflow_runs_workflow_id", "workflow_runs", ["workflow_id"])
    op.create_index("ix_workflow_runs_started", "workflow_runs", ["started_at"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=30), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="4", nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], name="fk_jobs_run_id_workflow_runs", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.UniqueConstraint("idempotency_key", name="uq_jobs_idempotency_key"),
        sa.CheckConstraint("status IN ('pending', 'running', 'done', 'failed', 'cancelled')", name="ck_jobs_job_status_known"),
    )
    op.create_index("ix_jobs_run_id", "jobs", ["run_id"])
    op.create_index("ix_jobs_due", "jobs", ["status", "run_at"])
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=12), server_default="task", nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_tasks_customer_id_customers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], name="fk_tasks_run_id_workflow_runs", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_tasks"),
        sa.CheckConstraint("kind IN ('task', 'notification')", name="ck_tasks_task_kind_known"),
    )
    op.create_index("ix_tasks_customer_id", "tasks", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_customer_id", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_jobs_due", table_name="jobs")
    op.drop_index("ix_jobs_run_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_workflow_runs_started", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workflow_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_table("workflows")
