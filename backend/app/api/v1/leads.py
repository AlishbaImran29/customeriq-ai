"""Leads: the pipeline, adding and moving leads, converting them, and a test mode for Meta Lead Ads."""

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models.lead import STAGES, Lead, LeadEvent
from app.schemas.imports import CamelModel
from app.services import leads as service

router = APIRouter(prefix="/leads", tags=["leads"])

Stage = Literal["new", "contacted", "interested", "converted", "lost"]


class LeadOut(CamelModel):
    id: int
    name: str | None
    phone: str | None
    email: str | None
    source: str
    campaign: str | None
    utm_source: str | None
    utm_medium: str | None
    utm_campaign: str | None
    product_interest: str | None
    stage: Stage
    notes: str | None
    lost_reason: str | None
    customer_id: int | None
    follow_up_at: datetime | None
    contacted_at: datetime | None
    created_at: datetime
    overdue: bool
    allowed_next: list[str]


class LeadIn(CamelModel):
    name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=320)
    campaign: str | None = Field(default=None, max_length=160)
    utm_source: str | None = Field(default=None, max_length=100)
    utm_medium: str | None = Field(default=None, max_length=100)
    utm_campaign: str | None = Field(default=None, max_length=160)
    product_interest: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)


class MoveIn(CamelModel):
    stage: Stage
    lost_reason: str | None = Field(default=None, max_length=200)
    follow_up_in_hours: int | None = Field(default=None, ge=1, le=24 * 60)


class NoteIn(CamelModel):
    notes: str = Field(max_length=1000)


class MetaTestIn(CamelModel):
    leadgen_id: str = Field(min_length=1, max_length=60)
    field_data: list[dict[str, Any]]
    campaign: str | None = Field(default=None, max_length=160)


class EventOut(CamelModel):
    event: str
    detail: dict[str, Any]
    at: datetime


def _out(lead: Lead, settings: Settings, now: datetime) -> LeadOut:
    late = lead.stage == "new" and lead.created_at <= now - timedelta(hours=settings.lead_sla_hours)
    return LeadOut(
        id=lead.id, name=lead.name, phone=lead.phone, email=lead.email, source=lead.source, campaign=lead.campaign, utm_source=lead.utm_source, utm_medium=lead.utm_medium,
        utm_campaign=lead.utm_campaign, product_interest=lead.product_interest, stage=lead.stage, notes=lead.notes, lost_reason=lead.lost_reason,  # type: ignore[arg-type]
        customer_id=lead.customer_id, follow_up_at=lead.follow_up_at, contacted_at=lead.contacted_at, created_at=lead.created_at, overdue=late,
        allowed_next=list(service.TRANSITIONS[lead.stage]),
    )


def _get(db: Session, lead_id: int) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise ApiError(404, "lead_not_found", "No such lead.")
    return lead


@router.get("", response_model=list[LeadOut], summary="Leads, newest first")
def list_leads(stage: Stage | None = Query(None), db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> list[LeadOut]:
    query = select(Lead).order_by(Lead.id.desc()).limit(300)
    if stage:
        query = query.where(Lead.stage == stage)
    now = datetime.now(timezone.utc)
    return [_out(lead, settings, now) for lead in db.scalars(query)]


@router.get("/summary", summary="How many leads are in each stage, and how many are overdue")
def summary(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    counts = dict(db.execute(select(Lead.stage, func.count()).group_by(Lead.stage)).all())
    return {"stages": {s: int(counts.get(s, 0)) for s in STAGES}, "overdue": len(service.overdue(db, settings, datetime.now(timezone.utc))), "slaHours": settings.lead_sla_hours}


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED, summary="Add a lead by hand")
def add(body: LeadIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> LeadOut:
    lead, created = service.create_lead(db, source="manual", **body.model_dump())
    if not created:
        raise ApiError(409, "lead_exists", "There is already an open lead with this phone number.", {"leadId": lead.id})
    db.commit()
    return _out(lead, settings, datetime.now(timezone.utc))


@router.post("/{lead_id}/move", response_model=LeadOut, summary="Move a lead to another stage (converting links it to a customer)")
def move(lead_id: int, body: MoveIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> LeadOut:
    now = datetime.now(timezone.utc)
    follow = now + timedelta(hours=body.follow_up_in_hours) if body.follow_up_in_hours else None
    lead = service.move(db, _get(db, lead_id), body.stage, lost_reason=body.lost_reason, follow_up_at=follow, now=now)
    db.commit()
    return _out(lead, settings, now)


@router.patch("/{lead_id}", response_model=LeadOut, summary="Change a lead's notes")
def notes(lead_id: int, body: NoteIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> LeadOut:
    lead = _get(db, lead_id)
    lead.notes = body.notes.strip() or None
    db.commit()
    return _out(lead, settings, datetime.now(timezone.utc))


@router.get("/{lead_id}/events", response_model=list[EventOut], summary="The lead's history")
def events(lead_id: int, db: Session = Depends(get_db)) -> list[LeadEvent]:
    _get(db, lead_id)
    return list(db.scalars(select(LeadEvent).where(LeadEvent.lead_id == lead_id).order_by(LeadEvent.id.desc())))


@router.post("/meta/test", response_model=LeadOut, status_code=status.HTTP_201_CREATED, summary="TEST MODE: run a Meta instant-form answer through the real code")
def meta_test(body: MetaTestIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> LeadOut:
    """The same function the real Meta webhook uses, fed by hand. Use it to try the flow without a Meta account."""
    lead, _ = service.from_meta_fields(db, body.leadgen_id, body.field_data, campaign=body.campaign)
    db.commit()
    return _out(lead, settings, datetime.now(timezone.utc))
