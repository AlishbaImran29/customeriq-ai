"""Auto Messenger, parts 5 and 6: journeys, and the results dashboard."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import Customer, Journey, JourneyEnrollment, Message, MessageTemplate
from app.schemas.messaging_automation import (
    ComparisonOut, CostOut, EnrollmentCounts, EnrollmentOut, GroupOut, JourneyOut, JourneyPatch, JourneyResultOut, ResultsOut,
    SeedJourneysOut, StepIn, TotalsOut,
)
from app.services.messaging import defaults, journey_defaults, journeys, results as results_service
from app.services.messaging.settings_store import get_row

router = APIRouter(prefix="/messaging", tags=["messaging"])


def _journey(db: Session, journey_id: int) -> Journey:
    journey = db.get(Journey, journey_id)
    if journey is None:
        raise ApiError(404, "journey_not_found", "That journey was not found.")
    return journey


def _journey_out(db: Session, j: Journey) -> JourneyOut:
    by_state = {s: n for s, n in db.execute(select(JourneyEnrollment.state, func.count()).where(JourneyEnrollment.journey_id == j.id).group_by(JourneyEnrollment.state))}
    stopped = {r: n for r, n in db.execute(select(JourneyEnrollment.stop_reason, func.count()).where(JourneyEnrollment.journey_id == j.id, JourneyEnrollment.state == "stopped").group_by(JourneyEnrollment.stop_reason)) if r}
    sent = db.scalar(select(func.count()).select_from(Message).where(Message.journey_id == j.id, Message.sent_at.is_not(None))) or 0
    events = {s["event"] for s in j.steps}
    approved = set(db.scalars(select(MessageTemplate.event).where(MessageTemplate.event.in_(events), MessageTemplate.approved_by_seller.is_(True)).distinct()))
    return JourneyOut(
        id=j.id, key=j.key, name=j.name, description=j.description, trigger_segment=j.trigger_segment, anchor=j.anchor,  # type: ignore[arg-type]
        steps=[StepIn(day=s["day"], event=s["event"]) for s in j.steps], loop_every_days=j.loop_every_days, max_sends=j.max_sends,
        max_per_30_days=j.max_per_30_days, grace_days=j.grace_days, enabled=j.enabled,
        counts=EnrollmentCounts(active=int(by_state.get("active", 0)), holdout=int(by_state.get("holdout", 0)), completed=int(by_state.get("completed", 0)), stopped=stopped),
        messages_sent=int(sent), templates_ready=events <= approved,
    )


@router.get("/journeys", response_model=list[JourneyOut], summary="Journeys")
def list_journeys(db: Session = Depends(get_db)) -> list[JourneyOut]:
    return [_journey_out(db, j) for j in db.scalars(select(Journey).order_by(Journey.id))]


@router.post("/journeys/seed-defaults", response_model=SeedJourneysOut, summary="Add the default journeys and their templates (all switched off, not approved)")
def seed_default_journeys(db: Session = Depends(get_db)) -> SeedJourneysOut:
    added = journeys.seed_journeys(db)
    templates = defaults.seed_defaults(db, [], journey_defaults.journey_templates())
    db.commit()
    return SeedJourneysOut(journeys=added, templates=templates)


@router.patch("/journeys/{journey_id}", response_model=JourneyOut, summary="Change a journey (including switching it on or off)")
def edit_journey(journey_id: int, body: JourneyPatch, db: Session = Depends(get_db)) -> JourneyOut:
    journey = _journey(db, journey_id)
    sent = body.model_fields_set
    for field in ("name", "description", "anchor", "grace_days"):
        if field in sent and getattr(body, field) is not None:
            setattr(journey, field, getattr(body, field))
    if "enabled" in sent and body.enabled is not None:
        journey.enabled = body.enabled
    for field in ("loop_every_days", "max_sends", "max_per_30_days"):
        if field in sent:
            setattr(journey, field, getattr(body, field))                 # None clears it
    if "steps" in sent and body.steps is not None:
        days = [s.day for s in body.steps]
        if days != sorted(days) or len(set(days)) != len(days):
            raise ApiError(422, "invalid_steps", "The steps must be in order, one per day, from the earliest day to the latest.")
        journey.steps = [{"day": s.day, "event": s.event} for s in body.steps]
    db.commit()
    return _journey_out(db, journey)


@router.get("/journeys/{journey_id}/enrollments", response_model=list[EnrollmentOut], summary="Who is on a journey")
def list_enrollments(
    journey_id: int, state: str | None = Query(default=None, pattern="^(active|completed|stopped|holdout)$"), db: Session = Depends(get_db),
) -> list[EnrollmentOut]:
    _journey(db, journey_id)
    query = select(JourneyEnrollment).where(JourneyEnrollment.journey_id == journey_id).order_by(JourneyEnrollment.id.desc()).limit(200)
    if state:
        query = query.where(JourneyEnrollment.state == state)
    rows = list(db.scalars(query))
    names = {c.id: (" ".join(p for p in (c.first_name, c.last_name) if p) or c.external_id) for c in db.scalars(select(Customer).where(Customer.id.in_({r.customer_id for r in rows})))} if rows else {}
    return [EnrollmentOut(id=r.id, customer_name=names.get(r.customer_id, "?"), state=r.state, holdout=r.holdout, stop_reason=r.stop_reason,  # type: ignore[arg-type]
                          step=r.step_index + 1, sends=r.sends, next_run_at=r.next_run_at, enrolled_at=r.enrolled_at) for r in rows]


@router.post("/journeys/run-now", summary="Run the journeys now (the same pass the scheduler makes)")
def run_journeys_now(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    result = journeys.run_journeys(db, settings)
    db.commit()
    return result


# =========================== results ===========================


def _cost(g: results_service.GroupStats, row) -> float | None:
    """WhatsApp cost of a group: its messages times the seller's own price per message. None when a needed price is missing."""
    parts = []
    for count, rate in ((g.whatsapp_utility, row.cost_utility), (g.whatsapp_marketing, row.cost_marketing)):
        if count:
            if rate is None:
                return None
            parts.append(count * float(rate))
    return round(sum(parts), 2)


def _group(g: results_service.GroupStats, row) -> GroupOut:
    return GroupOut(id=g.key, name=g.name, sent=g.sent, delivered=g.delivered, read=g.read, replied=g.replied, failed=g.failed, skipped=g.skipped,
                    opt_outs=g.opt_outs, orders=g.orders, revenue=round(g.revenue, 2), whatsapp_cost=_cost(g, row))


@router.get("/results", response_model=ResultsOut, summary="What the messages did")
def get_results(days: int = Query(default=90, ge=1, le=365), include_dry_run: bool = Query(default=False, alias="includeDryRun"), db: Session = Depends(get_db)) -> ResultsOut:
    data = results_service.build(db, days, include_dry_run)
    row = get_row(db)
    cost = data["cost"]
    needed = [(cost["utility_messages"], cost["utility_rate"]), (cost["marketing_messages"], cost["marketing_rate"])]
    total = None if any(count and rate is None for count, rate in needed) else round(sum(count * (rate or 0) for count, rate in needed), 2)
    return ResultsOut(
        days=days, include_dry_run=include_dry_run, min_group_count=results_service.MIN_MESSAGING_GROUP, totals=TotalsOut(**data["totals"]),
        cost=CostOut(**cost, total=total), templates=[_group(g, row) for g in data["templates"]], campaigns=[_group(g, row) for g in data["campaigns"]],
        journeys=[
            JourneyResultOut(journey_id=j.id, name=j.name, enabled=j.enabled, group=_group(group, row) if group else None, comparison=ComparisonOut(**asdict(comparison)))
            for j, group, comparison in data["journey_rows"]
        ],
    )
