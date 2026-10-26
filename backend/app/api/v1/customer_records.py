"""Customer records: notes and tags, a customer's timeline, erasing a customer, export, and the audit trail."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import Customer
from app.models.customer_audit import CustomerAudit
from app.schemas.imports import CamelModel
from app.services import customer_records as records

router = APIRouter(prefix="/customer-records", tags=["customer-records"])


class ProfileOut(CamelModel):
    id: int
    customer_id: str                       # the customer's id from the import (what the profile page uses)
    name: str
    email: str | None
    phone: str | None
    notes: str | None
    tags: list[str]
    acquisition_source: str | None
    status: Literal["active", "blocked", "anonymised"]


class ProfilePatch(CamelModel):
    notes: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = Field(default=None, max_length=50)
    acquisition_source: str | None = Field(default=None, max_length=60)
    status: Literal["active", "blocked"] | None = None


class EventOut(CamelModel):
    at: datetime
    kind: Literal["order", "status", "message", "reply", "consent"]
    text: str


class EraseIn(CamelModel):
    customer_id: str = Field(min_length=1, max_length=100)
    confirm: bool = False


class AuditOut(CamelModel):
    id: int
    action: str
    customer_ref: str
    detail: dict
    at: datetime


def _profile(c: Customer) -> ProfileOut:
    return ProfileOut(
        id=c.id, customer_id=c.external_id, name=records.display_name(c), email=c.email, phone=c.phone, notes=c.notes, tags=list(c.tags or []),
        acquisition_source=c.acquisition_source, status=c.status,  # type: ignore[arg-type]
    )


def _find(db: Session, external_id: str) -> Customer:
    customer = db.scalar(select(Customer).where(Customer.external_id == external_id))
    if customer is None:
        raise ApiError(404, "customer_not_found", "No customer with that ID.")
    return customer


def _confirmed(confirm: bool) -> None:
    if not confirm:
        raise ApiError(422, "confirmation_required", "Please confirm: this cannot be undone.")


@router.get("/profile", response_model=ProfileOut, summary="Notes, tags and source of one customer")
def get_profile(id: str = Query(..., min_length=1, max_length=100), db: Session = Depends(get_db)) -> ProfileOut:
    return _profile(_find(db, id))


@router.patch("/profile", response_model=ProfileOut, summary="Change notes, tags, source or status")
def patch_profile(body: ProfilePatch, id: str = Query(..., min_length=1, max_length=100), db: Session = Depends(get_db)) -> ProfileOut:
    customer = _find(db, id)
    if customer.status == "anonymised":
        raise ApiError(409, "customer_anonymised", "An erased customer cannot be changed.")
    changed = []
    data = body.model_dump(exclude_unset=True)
    if "notes" in data:
        customer.notes = data["notes"] or None
        changed.append("notes")
    if "tags" in data:
        customer.tags = records.clean_tags(data["tags"] or [])
        changed.append("tags")
    if "acquisition_source" in data:
        customer.acquisition_source = data["acquisition_source"] or None
        changed.append("acquisition_source")
    if data.get("status"):
        customer.status = data["status"]
        changed.append("status")
    if changed:
        records.audit(db, "edit", customer, fields=changed)
    db.commit()
    db.refresh(customer)
    return _profile(customer)


@router.get("/timeline", response_model=list[EventOut], summary="Orders, status changes, messages, replies and consent of one customer")
def get_timeline(id: str = Query(..., min_length=1, max_length=100), db: Session = Depends(get_db)) -> list[EventOut]:
    return [EventOut(at=e.at, kind=e.kind, text=e.text) for e in records.timeline(db, _find(db, id))]  # type: ignore[arg-type]


@router.post("/anonymise", response_model=ProfileOut, summary="Erase a customer's personal data but keep the orders as anonymous figures")
def anonymise(body: EraseIn, db: Session = Depends(get_db)) -> ProfileOut:
    _confirmed(body.confirm)
    customer = records.anonymise(db, get_settings(), _find(db, body.customer_id).id)
    db.commit()
    db.refresh(customer)
    return _profile(customer)


@router.post("/delete", status_code=204, summary="Delete a customer and their orders")
def delete(body: EraseIn, db: Session = Depends(get_db)) -> Response:
    _confirmed(body.confirm)
    records.delete_customer(db, get_settings(), _find(db, body.customer_id).id)
    db.commit()
    return Response(status_code=204)


@router.get("/export.csv", summary="All customers as a CSV file")
def export(db: Session = Depends(get_db)) -> Response:
    return Response(records.export_csv(db), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="customers.csv"'})


@router.get("/audit", response_model=list[AuditOut], summary="Edits, merges and erasures, newest first")
def audit_log(db: Session = Depends(get_db)) -> list[CustomerAudit]:
    return list(db.scalars(select(CustomerAudit).order_by(CustomerAudit.id.desc()).limit(200)))
