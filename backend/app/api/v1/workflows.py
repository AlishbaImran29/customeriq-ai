"""Automation engine endpoints: build and test workflows, switch them on, read the logs, retry failed steps."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_user
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import Job, Task, Workflow, WorkflowRun
from app.models.messaging import MessageTemplate
from app.schemas.imports import CamelModel
from app.services.workflows import engine, spec

router = APIRouter(prefix="/workflows", tags=["workflows"])


# --- shapes ----------------------------------------------------------------------------------------------------------------


class Definition(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=300)
    trigger: str
    trigger_config: dict[str, Any] = {}
    conditions: dict[str, Any] = {}
    actions: list[dict[str, Any]]


class WorkflowOut(CamelModel):
    id: int
    name: str
    description: str | None
    trigger: str
    trigger_config: dict[str, Any]
    conditions: dict[str, Any]
    actions: list[dict[str, Any]]
    enabled: bool
    version: int
    created_by: str | None
    runs: int = 0
    failed_runs: int = 0


class TestIn(CamelModel):
    definition: Definition
    order_id: int | None = None
    customer_id: int | None = None
    status: str | None = None
    text: str | None = None
    item_id: int | None = None


class JobOut(CamelModel):
    id: int
    step_index: int
    action_type: str
    run_at: datetime
    status: str
    attempts: int
    max_attempts: int
    last_error: str | None
    result: dict[str, Any] | None
    finished_at: datetime | None


class RunOut(CamelModel):
    id: int
    workflow_id: int
    workflow_name: str
    workflow_version: int
    event_key: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    context: dict[str, Any]
    jobs: list[JobOut] = []


class FailedJobOut(JobOut):
    run_id: int
    workflow_name: str


class TaskOut(CamelModel):
    id: int
    kind: str
    title: str
    detail: str | None
    customer_id: int | None
    due_at: datetime | None
    done: bool
    created_at: datetime


# --- helpers ---------------------------------------------------------------------------------------------------------------


def _problems(d: Definition) -> list[str]:
    return spec.check(d.trigger, d.trigger_config, d.conditions, d.actions)


def _require_valid(d: Definition) -> None:
    problems = _problems(d)
    if problems:
        raise ApiError(422, "invalid_workflow", problems[0], {"problems": problems})


def _out(db: Session, w: Workflow) -> WorkflowOut:
    runs = db.scalar(select(func.count()).select_from(WorkflowRun).where(WorkflowRun.workflow_id == w.id)) or 0
    failed = db.scalar(select(func.count()).select_from(WorkflowRun).where(WorkflowRun.workflow_id == w.id, WorkflowRun.status == "failed")) or 0
    return WorkflowOut(
        id=w.id, name=w.name, description=w.description, trigger=w.trigger, trigger_config=w.trigger_config or {}, conditions=w.conditions or {},
        actions=w.actions or [], enabled=w.enabled, version=w.version, created_by=w.created_by, runs=runs, failed_runs=failed,
    )


def _get(db: Session, workflow_id: int) -> Workflow:
    w = db.get(Workflow, workflow_id)
    if w is None:
        raise ApiError(404, "workflow_not_found", "No such workflow.")
    return w


def _job_out(j: Job) -> JobOut:
    return JobOut(id=j.id, step_index=j.step_index, action_type=j.action_type, run_at=j.run_at, status=j.status, attempts=j.attempts, max_attempts=j.max_attempts,
                  last_error=j.last_error, result=j.result, finished_at=j.finished_at)


# --- what the builder may offer -------------------------------------------------------------------------------------------------


@router.get("/meta", summary="Everything the builder may offer: triggers, condition fields, operators, actions, message events")
def meta(db: Session = Depends(get_db)) -> dict[str, Any]:
    events = sorted({e for (e,) in db.execute(select(MessageTemplate.event).where(MessageTemplate.event.is_not(None)).distinct())})
    return {
        "triggers": [{"id": k, "label": v[1], "carries": sorted(v[0])} for k, v in spec.TRIGGERS.items()],
        "fields": [{"id": k, "type": v[0], "needs": v[1], "label": v[2], "operators": sorted(spec.OPERATORS[v[0]])} for k, v in spec.FIELDS.items()],
        "operatorLabels": spec.OPERATOR_LABELS,
        "actions": [{"id": k, "label": v[1], "needs": sorted(v[0])} for k, v in spec.ACTIONS.items()],
        "orderStatuses": list(spec.UPDATABLE_STATUSES),
        "messageEvents": events,
        "limits": {"maxRules": spec.MAX_RULES, "maxActions": spec.MAX_ACTIONS, "maxDelayMinutes": spec.MAX_DELAY_MINUTES},
    }


@router.post("/validate", summary="Every problem with a definition, in plain words")
def validate(body: Definition) -> dict[str, Any]:
    problems = _problems(body)
    return {"valid": not problems, "problems": problems}


@router.post("/test", summary="Test run: what would happen for this order or customer (nothing is changed or sent)")
def test_run(body: TestIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    _require_valid(body.definition)
    payload = {k: v for k, v in (("order_id", body.order_id), ("customer_id", body.customer_id), ("status", body.status), ("text", body.text), ("item_id", body.item_id)) if v is not None}
    return engine.dry_run(db, settings, body.definition.model_dump(), payload)


# --- workflows ------------------------------------------------------------------------------------------------------------------


@router.get("", response_model=list[WorkflowOut], summary="All workflows")
def list_workflows(db: Session = Depends(get_db)) -> list[WorkflowOut]:
    return [_out(db, w) for w in db.scalars(select(Workflow).order_by(Workflow.id.desc()))]


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED, summary="Save a new workflow (switched off)")
def create(body: Definition, db: Session = Depends(get_db), user=Depends(require_user)) -> WorkflowOut:
    _require_valid(body)
    w = Workflow(name=body.name.strip(), description=body.description, trigger=body.trigger, trigger_config=body.trigger_config, conditions=body.conditions,
                 actions=body.actions, enabled=False, version=1, created_by=getattr(user, "email", None))
    db.add(w)
    db.commit()
    db.refresh(w)
    return _out(db, w)


@router.put("/{workflow_id}", response_model=WorkflowOut, summary="Change a workflow (its version goes up)")
def update(workflow_id: int, body: Definition, db: Session = Depends(get_db)) -> WorkflowOut:
    _require_valid(body)
    w = _get(db, workflow_id)
    changed = (w.trigger, w.trigger_config, w.conditions, w.actions) != (body.trigger, body.trigger_config, body.conditions, body.actions)
    w.name, w.description = body.name.strip(), body.description
    w.trigger, w.trigger_config, w.conditions, w.actions = body.trigger, body.trigger_config, body.conditions, body.actions
    if changed:
        w.version += 1
    db.commit()
    db.refresh(w)
    return _out(db, w)


@router.post("/{workflow_id}/enable", response_model=WorkflowOut, summary="Switch on (it must be valid)")
def enable(workflow_id: int, db: Session = Depends(get_db)) -> WorkflowOut:
    w = _get(db, workflow_id)
    problems = spec.check(w.trigger, w.trigger_config, w.conditions, w.actions)
    if problems:
        raise ApiError(422, "invalid_workflow", problems[0], {"problems": problems})
    w.enabled = True
    db.commit()
    return _out(db, w)


@router.post("/{workflow_id}/disable", response_model=WorkflowOut, summary="Pause: no new runs, and waiting steps are held until it is switched on again")
def disable(workflow_id: int, db: Session = Depends(get_db)) -> WorkflowOut:
    w = _get(db, workflow_id)
    w.enabled = False
    db.commit()
    return _out(db, w)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a workflow and its logs")
def delete(workflow_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(_get(db, workflow_id))
    db.commit()


# --- logs and the queue ---------------------------------------------------------------------------------------------------------


@router.get("/runs/list", response_model=list[RunOut], summary="Recent runs (without steps)")
def runs(workflow_id: int | None = Query(None, alias="workflowId"), run_status: str | None = Query(None, alias="status"), db: Session = Depends(get_db)) -> list[RunOut]:
    query = select(WorkflowRun, Workflow.name).join(Workflow, Workflow.id == WorkflowRun.workflow_id).order_by(WorkflowRun.id.desc()).limit(100)
    if workflow_id:
        query = query.where(WorkflowRun.workflow_id == workflow_id)
    if run_status:
        query = query.where(WorkflowRun.status == run_status)
    return [RunOut(id=r.id, workflow_id=r.workflow_id, workflow_name=name, workflow_version=r.workflow_version, event_key=r.event_key, status=r.status,
                   started_at=r.started_at, finished_at=r.finished_at, context=r.context or {}) for r, name in db.execute(query)]


@router.get("/runs/{run_id}", response_model=RunOut, summary="One run with every step")
def run_detail(run_id: int, db: Session = Depends(get_db)) -> RunOut:
    r = db.get(WorkflowRun, run_id)
    if r is None:
        raise ApiError(404, "run_not_found", "No such run.")
    w = db.get(Workflow, r.workflow_id)
    jobs = db.scalars(select(Job).where(Job.run_id == r.id).order_by(Job.step_index))
    return RunOut(id=r.id, workflow_id=r.workflow_id, workflow_name=w.name if w else "?", workflow_version=r.workflow_version, event_key=r.event_key,
                  status=r.status, started_at=r.started_at, finished_at=r.finished_at, context=r.context or {}, jobs=[_job_out(j) for j in jobs])


@router.post("/runs/{run_id}/cancel", response_model=RunOut, summary="Stop a run: its waiting steps are cancelled")
def cancel(run_id: int, db: Session = Depends(get_db)) -> RunOut:
    engine.cancel_run(db, run_id)
    db.commit()
    return run_detail(run_id, db)


@router.get("/jobs/failed", response_model=list[FailedJobOut], summary="Steps that failed for good, newest first")
def failed_jobs(db: Session = Depends(get_db)) -> list[FailedJobOut]:
    rows = db.execute(
        select(Job, WorkflowRun.id, Workflow.name).join(WorkflowRun, WorkflowRun.id == Job.run_id).join(Workflow, Workflow.id == WorkflowRun.workflow_id)
        .where(Job.status == "failed").order_by(Job.id.desc()).limit(100)
    )
    return [FailedJobOut(**_job_out(j).model_dump(), run_id=run_id, workflow_name=name) for j, run_id, name in rows]


@router.post("/jobs/{job_id}/retry", response_model=JobOut, summary="Try a failed step again")
def retry(job_id: int, db: Session = Depends(get_db)) -> JobOut:
    job = engine.retry_job(db, job_id)
    db.commit()
    return _job_out(job)


@router.post("/run-due", summary="Run the steps that are due now (the scheduler does this every hour)")
def run_due(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict[str, int]:
    return engine.run_due_jobs(db, settings)


@router.get("/tasks/list", response_model=list[TaskOut], summary="To-dos and notifications made by workflows")
def tasks(show_done: bool = Query(False, alias="showDone"), db: Session = Depends(get_db)) -> list[Task]:
    query = select(Task).order_by(Task.id.desc()).limit(200)
    if not show_done:
        query = query.where(Task.done.is_(False))
    return list(db.scalars(query))


@router.post("/tasks/{task_id}/done", response_model=TaskOut, summary="Tick a to-do off")
def task_done(task_id: int, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise ApiError(404, "task_not_found", "No such to-do.")
    task.done = True
    db.commit()
    return task

