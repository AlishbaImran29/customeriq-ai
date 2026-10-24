"""The automation engine: events in, durable jobs out, a worker that runs them.

HOW IT WORKS (this is the part to explain in the viva)
1. Somewhere in the app something happens (an order is added, a status changes...) and calls `emit(trigger, ids)`.
   `emit` NEVER raises and runs in a savepoint, so a broken workflow can never roll back or fail the order that caused it.
2. For every ENABLED workflow with that trigger: gather the facts its conditions ask about, check the conditions, and if
   they hold start a RUN. A run is unique per (workflow, event_key), so the same event twice never starts two runs.
3. A run is a chain of JOBS in the `jobs` table, one per action. The first is queued for "now + its delay". When a step
   succeeds the next one is queued for "now + the next delay". The table is the queue, so it survives restarts.
4. `run_due_jobs` (called by the scheduler, or by the "run now" button) takes due jobs with FOR UPDATE SKIP LOCKED (two
   workers never get the same job), runs each in its own savepoint, and records the result. A step that fails is retried
   with growing waits (5, 10, 20 minutes), up to its maximum; a step that can never work (no template, a web address that
   is not approved) fails at once. A seller can retry a failed job, cancel a run, or pause a workflow (disable it).
5. A job found "running" for over 10 minutes (the worker died) is put back in the queue. Steps are safe to repeat: messages
   have idempotency keys, tags are sets, and an order status that is already set changes nothing.

LOOP PROTECTION. Work done by a workflow (say, changing an order's status) can itself be an event. Each run remembers the
chain of workflows that led to it: a workflow already in the chain is skipped, and a chain is at most MAX_DEPTH long.
"""

import logging
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import Customer, Order
from app.models.journey import SchedulerState
from app.models.workflow import Job, Workflow, WorkflowRun
from app.services.messaging import policy
from app.services.messaging.settings_store import get_row
from app.services.workflows import actions, conditions, facts
from app.services.workflows.spec import MAX_DEPTH, TRIGGERS

logger = logging.getLogger(__name__)

STALE_RUNNING_MINUTES = 10
BACKOFF_MINUTES = 5                       # waits: 5, 10, 20...
_chain: ContextVar[tuple[int, ...]] = ContextVar("workflow_chain", default=())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# --- events in -----------------------------------------------------------------------------------------------------------


def emit(db: Session, settings: Settings, trigger: str, payload: dict[str, Any], event_key: str, now: datetime | None = None) -> list[WorkflowRun]:
    """Tell the engine something happened. Never raises. Commits nothing: the caller's transaction decides."""
    try:
        with db.begin_nested():
            return _emit(db, trigger, payload, event_key, now or now_utc())
    except Exception:  # noqa: BLE001 (an automation problem must never break the thing that happened)
        logger.exception("Workflow emit failed for %s", trigger)
        return []


def _emit(db: Session, trigger: str, payload: dict[str, Any], event_key: str, now: datetime) -> list[WorkflowRun]:
    chain = _chain.get()
    if trigger not in TRIGGERS or len(chain) >= MAX_DEPTH:
        return []
    query = select(Workflow).where(Workflow.enabled.is_(True), Workflow.trigger == trigger)
    if chain:
        query = query.where(Workflow.id.not_in(chain))
    runs = []
    for workflow in db.scalars(query):
        run = fire(db, workflow, payload, event_key, now, chain)
        if run is not None:
            runs.append(run)
    return runs


def fire(db: Session, workflow: Workflow, payload: dict[str, Any], event_key: str, now: datetime, chain: tuple[int, ...] = ()) -> WorkflowRun | None:
    """Check one workflow's conditions for one event and start a run. None when the conditions do not hold or the event was already seen."""
    seen = facts.build(db, payload, conditions.fields_used(workflow.conditions))
    matched, _ = conditions.evaluate(workflow.conditions, seen)
    if not matched:
        return None
    run = WorkflowRun(workflow_id=workflow.id, workflow_version=workflow.version, event_key=event_key[:160], context={"payload": payload, "facts": seen}, chain=list(chain), status="running")
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:
        return None                                  # this event already started this workflow
    _queue_step(db, run, workflow.actions, 0, now)
    return run


def _queue_step(db: Session, run: WorkflowRun, steps: list, index: int, now: datetime) -> Job | None:
    if index >= len(steps):
        run.status, run.finished_at = ("failed" if _any_failed(db, run) else "done"), now
        return None
    step = steps[index]
    job = Job(run_id=run.id, step_index=index, action_type=step["type"], run_at=now + timedelta(minutes=int(step.get("delayMinutes", 0))), idempotency_key=f"run:{run.id}:step:{index}")
    db.add(job)
    db.flush()
    return job


def _any_failed(db: Session, run: WorkflowRun) -> bool:
    return db.scalar(select(func.count()).select_from(Job).where(Job.run_id == run.id, Job.status == "failed")) > 0


# --- the worker ------------------------------------------------------------------------------------------------------------


def _claim(db: Session, now: datetime) -> Job | None:
    return db.scalar(
        select(Job).join(WorkflowRun, WorkflowRun.id == Job.run_id).join(Workflow, Workflow.id == WorkflowRun.workflow_id)
        .where(Job.status == "pending", Job.run_at <= now, WorkflowRun.status == "running", Workflow.enabled.is_(True))
        .order_by(Job.run_at, Job.id).limit(1).with_for_update(skip_locked=True, of=Job)
    )


def recover_stale(db: Session, now: datetime) -> int:
    """Jobs left "running" by a worker that died go back to the queue."""
    result = db.execute(update(Job).where(Job.status == "running", Job.started_at < now - timedelta(minutes=STALE_RUNNING_MINUTES)).values(status="pending", run_at=now))
    return result.rowcount or 0


def run_due_jobs(db: Session, settings: Settings, now: datetime | None = None, limit: int = 25) -> dict[str, int]:
    """Run the jobs that are due. Commits after every job, so a crash loses at most the job being run."""
    now = now or now_utc()
    counts = {"recovered": recover_stale(db, now), "done": 0, "retry": 0, "failed": 0}
    db.commit()
    for _ in range(limit):
        job = _claim(db, now)
        if job is None:
            break
        job.status, job.started_at, job.attempts = "running", now, job.attempts + 1
        db.flush()
        outcome = _execute(db, settings, job, now)
        counts[outcome] += 1
        db.commit()
    return counts


def _execute(db: Session, settings: Settings, job: Job, now: datetime) -> str:
    run = db.get(WorkflowRun, job.run_id)
    workflow = db.get(Workflow, run.workflow_id)
    step = workflow.actions[job.step_index]
    token = _chain.set(tuple(run.chain or []) + (workflow.id,))
    try:
        with db.begin_nested():
            result = actions.perform(db, settings, step, run.context.get("payload", {}), run_id=run.id, step=job.step_index, now=now)
    except actions.NonRetryable as exc:
        return _fail(db, job, run, str(exc), now)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Workflow step failed (run %s step %s)", run.id, job.step_index)
        if job.attempts >= job.max_attempts:
            return _fail(db, job, run, f"{type(exc).__name__}: {str(exc)[:200]}", now)
        job.status, job.last_error = "pending", f"{type(exc).__name__}: {str(exc)[:200]}"
        job.run_at = now + timedelta(minutes=BACKOFF_MINUTES * 2 ** (job.attempts - 1))
        return "retry"
    finally:
        _chain.reset(token)
    job.status, job.result, job.last_error, job.finished_at = "done", result, None, now
    _queue_step(db, run, workflow.actions, job.step_index + 1, now)
    return "done"


def _fail(db: Session, job: Job, run: WorkflowRun, error: str, now: datetime) -> str:
    job.status, job.last_error, job.finished_at = "failed", error[:300], now
    run.status, run.finished_at = "failed", now
    return "failed"


# --- the seller's controls -------------------------------------------------------------------------------------------------


def retry_job(db: Session, job_id: int, now: datetime | None = None) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise ApiError(404, "job_not_found", "No such job.")
    if job.status != "failed":
        raise ApiError(409, "not_failed", "Only a failed step can be retried.")
    run = db.get(WorkflowRun, job.run_id)
    job.status, job.attempts, job.run_at, job.finished_at = "pending", 0, now or now_utc(), None
    run.status, run.finished_at = "running", None
    db.flush()
    return job


def cancel_run(db: Session, run_id: int, now: datetime | None = None) -> WorkflowRun:
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise ApiError(404, "run_not_found", "No such run.")
    if run.status != "running":
        raise ApiError(409, "not_running", "This run is already finished.")
    db.execute(update(Job).where(Job.run_id == run.id, Job.status.in_(("pending", "running"))).values(status="cancelled", finished_at=now or now_utc()))
    run.status, run.finished_at = "cancelled", now or now_utc()
    db.flush()
    return run


# --- the test run --------------------------------------------------------------------------------------------------------------


def dry_run(db: Session, settings: Settings, definition: dict, payload: dict[str, Any]) -> dict[str, Any]:
    """Pretend the trigger happened with this payload: would the conditions hold, and what would each step do? Changes nothing."""
    from app.services.workflows.spec import FIELDS

    seen = facts.build(db, payload, set(FIELDS))
    matched, trace = conditions.evaluate(definition.get("conditions"), seen)
    steps = []
    for i, step in enumerate(definition["actions"]):
        steps.append({"index": i, "type": step["type"], "delayMinutes": int(step.get("delayMinutes", 0)), "wouldDo": actions.describe(db, settings, step, payload)})
    return {"matched": matched, "trace": trace, "facts": seen, "steps": steps if matched else []}


# --- the clock: schedule triggers and "customer inactive" -------------------------------------------------------------------


def tick(db: Session, settings: Settings, now: datetime | None = None) -> dict[str, int]:
    """Once-a-day work: the daily and weekly triggers, and the scan for customers who stopped ordering."""
    now = now or now_utc()
    counts = {"daily": 0, "weekly": 0, "inactive": 0}
    today = now.astimezone(policy.zone(get_row(db).timezone)).date()
    for key, trigger, due in (("wf_daily", "schedule_daily", True), ("wf_weekly", "schedule_weekly", today.weekday() == 0)):
        state = db.get(SchedulerState, key)
        if not due or (state is not None and state.value == today.isoformat()):
            continue
        runs = emit(db, settings, trigger, {}, f"{trigger}:{today.isoformat()}", now)
        counts["daily" if key == "wf_daily" else "weekly"] = len(runs)
        if state is None:
            db.add(SchedulerState(key=key, value=today.isoformat()))
        else:
            state.value = today.isoformat()
    for workflow in db.scalars(select(Workflow).where(Workflow.enabled.is_(True), Workflow.trigger == "customer_inactive")):
        days = int((workflow.trigger_config or {}).get("days", 60))
        cutoff = today - timedelta(days=days)
        last = (
            select(Order.customer_id, func.max(Order.order_date).label("last")).group_by(Order.customer_id).having(func.max(Order.order_date) <= cutoff).subquery()
        )
        for customer_id, last_order in db.execute(
            select(Customer.id, last.c.last).join(last, last.c.customer_id == Customer.id).where(Customer.status == "active").order_by(last.c.last.desc()).limit(200)
        ):
            if fire(db, workflow, {"customer_id": customer_id}, f"inactive:{customer_id}:{last_order.isoformat()}", now) is not None:
                counts["inactive"] += 1
    db.flush()
    return counts
