"""The automation engine's tables: workflows, their runs, the durable job queue, and the seller's to-do list."""

import datetime as dt

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Workflow(TimestampMixin, Base):
    """When [trigger] happens and [conditions] hold, do [actions] one after another, each after its own delay.
    `conditions` and `actions` are plain JSON checked against an allowlist (services/workflows/spec.py): no code is ever run."""

    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(300))
    trigger: Mapped[str] = mapped_column(String(30))
    trigger_config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")    # e.g. {"days": 60} for "customer inactive"
    conditions: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")        # {"op": "and", "rules": [{"field", "operator", "value"}]}
    actions: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")           # [{"type", "params", "delayMinutes"}]
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")              # +1 on every change to the definition
    created_by: Mapped[str | None] = mapped_column(String(320))


class WorkflowRun(Base):
    """One time a workflow fired for one event. `context` is the facts it saw at that moment, kept so the log is explainable."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint("workflow_id", "event_key", name="uq_workflow_runs_workflow_event"),
        CheckConstraint("status IN ('running', 'done', 'failed', 'cancelled')", name="run_status_known"),
        Index("ix_workflow_runs_started", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    workflow_version: Mapped[int] = mapped_column(Integer)
    event_key: Mapped[str] = mapped_column(String(160))
    context: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    chain: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")        # ids of the workflows that led to this one (loop protection)
    status: Mapped[str] = mapped_column(String(10), default="running", server_default="running")
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Job(Base):
    """One step of one run, waiting for its time. This table IS the queue: it survives restarts, and a worker takes a job with
    SELECT ... FOR UPDATE SKIP LOCKED so two workers never run the same step. `idempotency_key` is unique, so a step is never queued twice."""

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_jobs_idempotency_key"),
        CheckConstraint("status IN ('pending', 'running', 'done', 'failed', 'cancelled')", name="job_status_known"),
        Index("ix_jobs_due", "status", "run_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True)
    step_index: Mapped[int] = mapped_column(Integer)
    action_type: Mapped[str] = mapped_column(String(30))
    run_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=4, server_default="4")
    idempotency_key: Mapped[str] = mapped_column(String(80))
    last_error: Mapped[str | None] = mapped_column(String(300))
    result: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Task(Base):
    """A to-do or a notification for the seller, made by a workflow ("phone this customer")."""

    __tablename__ = "tasks"
    __table_args__ = (CheckConstraint("kind IN ('task', 'notification')", name="task_kind_known"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(12), default="task", server_default="task")
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str | None] = mapped_column(Text)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_runs.id", ondelete="SET NULL"))
    due_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    done: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
