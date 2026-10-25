"""Returns, refunds and complaint tickets."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_user
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import Customer, Order
from app.models.returns import Refund, ReturnEvent, ReturnEvidence, ReturnRequest, Ticket, TicketNote
from app.schemas.imports import CamelModel
from app.services import order_status, returns as service, supabase_storage

router = APIRouter(tags=["returns"])


def _who(user) -> str | None:
    return getattr(user, "email", None)


def _name(c: Customer | None) -> str:
    return (" ".join(p for p in (c.first_name, c.last_name) if p) or c.external_id) if c else "?"


# --- shapes ------------------------------------------------------------------------------------------------------------------------


class EvidenceOut(CamelModel):
    id: int
    kind: str
    mime_type: str
    size_bytes: int
    at: datetime
    url: str | None


class EventOut(CamelModel):
    event: str
    detail: dict[str, Any]
    by: str | None
    at: datetime


class RefundOut(CamelModel):
    id: int
    return_id: int | None
    order_id: int
    order_number: str
    amount: float
    status: Literal["requested", "recorded"]
    method: str | None
    reference: str | None
    recorded_at: datetime | None


class ReturnOut(CamelModel):
    id: int
    order_id: int
    order_number: str
    customer_name: str
    order_total: float
    reason: str
    status: Literal["requested", "approved", "rejected", "received", "closed"]
    resolution: str | None
    decision_note: str | None
    restocked: bool
    replacement_order_id: int | None
    created_at: datetime
    evidence: list[EvidenceOut] = []
    events: list[EventOut] = []
    refunds: list[RefundOut] = []


class ReturnIn(CamelModel):
    order_id: int
    reason: str = Field(min_length=3, max_length=300)


class ApproveIn(CamelModel):
    resolution: Literal["refund", "replacement", "none"]
    amount: Decimal | None = Field(default=None, ge=0, le=Decimal("9999999.99"))
    note: str | None = Field(default=None, max_length=300)


class RejectIn(CamelModel):
    note: str | None = Field(default=None, max_length=300)


class ReceiveIn(CamelModel):
    restock: bool = False


class RecordIn(CamelModel):
    method: str = Field(min_length=1, max_length=60)
    reference: str | None = Field(default=None, max_length=100)


# --- returns --------------------------------------------------------------------------------------------------------------------------


def _refund_out(db: Session, r: Refund) -> RefundOut:
    order = db.get(Order, r.order_id)
    return RefundOut(id=r.id, return_id=r.return_id, order_id=r.order_id, order_number=order_status.order_number(order) if order else "?", amount=float(r.amount),
                     status=r.status, method=r.method, reference=r.reference, recorded_at=r.recorded_at)  # type: ignore[arg-type]


def _return_out(db: Session, settings: Settings, ret: ReturnRequest, detail: bool = False) -> ReturnOut:
    order, customer = db.get(Order, ret.order_id), db.get(Customer, ret.customer_id)
    out = ReturnOut(
        id=ret.id, order_id=ret.order_id, order_number=order_status.order_number(order) if order else "?", customer_name=_name(customer), order_total=float(order.order_value) if order else 0.0,
        reason=ret.reason, status=ret.status, resolution=ret.resolution, decision_note=ret.decision_note, restocked=ret.restocked,  # type: ignore[arg-type]
        replacement_order_id=ret.replacement_order_id, created_at=ret.created_at,
    )
    if detail:
        out.evidence = [EvidenceOut(id=e.id, kind=e.kind, mime_type=e.mime_type, size_bytes=e.size_bytes, at=e.at, url=supabase_storage.signed_url_in(settings, settings.supabase_evidence_bucket, e.storage_path))
                        for e in db.scalars(select(ReturnEvidence).where(ReturnEvidence.return_id == ret.id).order_by(ReturnEvidence.id))]
        out.events = [EventOut(event=e.event, detail=e.detail, by=e.by, at=e.at) for e in db.scalars(select(ReturnEvent).where(ReturnEvent.return_id == ret.id).order_by(ReturnEvent.id.desc()))]
        out.refunds = [_refund_out(db, r) for r in db.scalars(select(Refund).where(Refund.return_id == ret.id).order_by(Refund.id))]
    return out


def _get(db: Session, return_id: int) -> ReturnRequest:
    ret = db.get(ReturnRequest, return_id)
    if ret is None:
        raise ApiError(404, "return_not_found", "No such return.")
    return ret


@router.get("/returns", response_model=list[ReturnOut], summary="Return requests, newest first")
def list_returns(state: str | None = Query(None, alias="status", pattern="^(requested|approved|rejected|received|closed)$"), db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> list[ReturnOut]:
    query = select(ReturnRequest).order_by(ReturnRequest.id.desc()).limit(200)
    if state:
        query = query.where(ReturnRequest.status == state)
    return [_return_out(db, settings, r) for r in db.scalars(query)]


@router.get("/returns/{return_id}", response_model=ReturnOut, summary="One return with evidence, history and refunds")
def get_return(return_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> ReturnOut:
    return _return_out(db, settings, _get(db, return_id), detail=True)


@router.post("/returns", response_model=ReturnOut, status_code=status.HTTP_201_CREATED, summary="Record a return request")
def create_return(body: ReturnIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings), user=Depends(require_user)) -> ReturnOut:
    ret = service.request_return(db, body.order_id, body.reason, _who(user))
    db.commit()
    return _return_out(db, settings, ret, detail=True)


@router.post("/returns/{return_id}/approve", response_model=ReturnOut, summary="Approve, and choose refund, replacement or nothing")
def approve(return_id: int, body: ApproveIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings), user=Depends(require_user)) -> ReturnOut:
    ret = service.approve(db, settings, _get(db, return_id), body.resolution, amount=body.amount, note=body.note, by=_who(user))
    db.commit()
    return _return_out(db, settings, ret, detail=True)


@router.post("/returns/{return_id}/reject", response_model=ReturnOut, summary="Reject the request")
def reject(return_id: int, body: RejectIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings), user=Depends(require_user)) -> ReturnOut:
    ret = service.reject(db, settings, _get(db, return_id), body.note, by=_who(user))
    db.commit()
    return _return_out(db, settings, ret, detail=True)


@router.post("/returns/{return_id}/receive", response_model=ReturnOut, summary="The goods came back; say whether they go back on the shelf")
def receive(return_id: int, body: ReceiveIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings), user=Depends(require_user)) -> ReturnOut:
    ret = service.receive(db, _get(db, return_id), body.restock, by=_who(user))
    db.commit()
    return _return_out(db, settings, ret, detail=True)


@router.post("/returns/{return_id}/close", response_model=ReturnOut, summary="Close a finished return")
def close(return_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings), user=Depends(require_user)) -> ReturnOut:
    ret = service.close(db, _get(db, return_id), by=_who(user))
    db.commit()
    return _return_out(db, settings, ret, detail=True)


@router.post("/returns/{return_id}/evidence", response_model=EvidenceOut, status_code=status.HTTP_201_CREATED, summary="Attach a photo or short video")
async def add_evidence(return_id: int, file: UploadFile, db: Session = Depends(get_db), settings: Settings = Depends(get_settings), user=Depends(require_user)) -> EvidenceOut:
    ret = _get(db, return_id)
    if db.scalar(select(ReturnEvidence.id).where(ReturnEvidence.return_id == ret.id).offset(service.MAX_EVIDENCE - 1).limit(1)) is not None:
        raise ApiError(409, "too_many_files", f"At most {service.MAX_EVIDENCE} files per return.")
    content = await file.read(service.MAX_VIDEO_BYTES + 1)
    mime = (file.content_type or "").lower()
    kind = service.check_evidence(content, mime)
    extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "video/mp4": "mp4"}[mime]
    path = f"returns/{ret.id}/{uuid.uuid4().hex}.{extension}"            # a random name: the customer's file name is never used
    await run_in_threadpool(supabase_storage.put_object, settings, settings.supabase_evidence_bucket, path, content, mime)
    evidence = ReturnEvidence(return_id=ret.id, storage_path=path, kind=kind, mime_type=mime, size_bytes=len(content))
    db.add(evidence)
    db.add(ReturnEvent(return_id=ret.id, event="evidence_added", by=_who(user), detail={"kind": kind, "bytes": len(content)}))
    db.commit()
    return EvidenceOut(id=evidence.id, kind=kind, mime_type=mime, size_bytes=len(content), at=evidence.at, url=supabase_storage.signed_url_in(settings, settings.supabase_evidence_bucket, path))


# --- refunds ------------------------------------------------------------------------------------------------------------------------


@router.get("/refunds", response_model=list[RefundOut], summary="Refunds asked for and recorded")
def list_refunds(state: str | None = Query(None, alias="status", pattern="^(requested|recorded)$"), db: Session = Depends(get_db)) -> list[RefundOut]:
    query = select(Refund).order_by(Refund.id.desc()).limit(200)
    if state:
        query = query.where(Refund.status == state)
    return [_refund_out(db, r) for r in db.scalars(query)]


@router.post("/refunds/{refund_id}/record", response_model=RefundOut, summary="I paid this refund back myself: record how")
def record_refund(refund_id: int, body: RecordIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings), user=Depends(require_user)) -> RefundOut:
    """The app never moves money. This only records that YOU did, and how."""
    refund = db.get(Refund, refund_id)
    if refund is None:
        raise ApiError(404, "refund_not_found", "No such refund.")
    service.record_refund(db, settings, refund, body.method, body.reference, by=_who(user))
    db.commit()
    return _refund_out(db, refund)


# --- tickets ------------------------------------------------------------------------------------------------------------------------


class NoteOut(CamelModel):
    id: int
    author: str | None
    text: str
    at: datetime


class TicketOut(CamelModel):
    id: int
    customer_id: int | None
    customer_name: str | None
    order_id: int | None
    subject: str
    body: str | None
    status: Literal["open", "in_progress", "resolved", "closed"]
    priority: Literal["low", "normal", "high"]
    assigned_to: str | None
    created_at: datetime
    resolved_at: datetime | None
    notes: list[NoteOut] = []


class TicketIn(CamelModel):
    subject: str = Field(min_length=3, max_length=200)
    body: str | None = Field(default=None, max_length=4000)
    customer_id: int | None = None
    order_id: int | None = None
    priority: Literal["low", "normal", "high"] = "normal"


class TicketPatch(CamelModel):
    status: Literal["open", "in_progress", "resolved", "closed"] | None = None
    priority: Literal["low", "normal", "high"] | None = None
    assigned_to: str | None = Field(default=None, max_length=320)


class NoteIn(CamelModel):
    text: str = Field(min_length=1, max_length=2000)


def _ticket_out(db: Session, t: Ticket, detail: bool = False) -> TicketOut:
    customer = db.get(Customer, t.customer_id) if t.customer_id else None
    out = TicketOut(id=t.id, customer_id=t.customer_id, customer_name=_name(customer) if customer else None, order_id=t.order_id, subject=t.subject, body=t.body,
                    status=t.status, priority=t.priority, assigned_to=t.assigned_to, created_at=t.created_at, resolved_at=t.resolved_at)  # type: ignore[arg-type]
    if detail:
        out.notes = [NoteOut(id=n.id, author=n.author, text=n.text, at=n.at) for n in db.scalars(select(TicketNote).where(TicketNote.ticket_id == t.id).order_by(TicketNote.id))]
    return out


def _ticket(db: Session, ticket_id: int) -> Ticket:
    t = db.get(Ticket, ticket_id)
    if t is None:
        raise ApiError(404, "ticket_not_found", "No such ticket.")
    return t


@router.get("/tickets", response_model=list[TicketOut], summary="Complaint tickets, open ones first")
def list_tickets(state: str | None = Query(None, alias="status", pattern="^(open|in_progress|resolved|closed)$"), db: Session = Depends(get_db)) -> list[TicketOut]:
    query = select(Ticket).limit(300)
    if state:
        query = query.where(Ticket.status == state)
    rows = list(db.scalars(query))
    rank = {"open": 0, "in_progress": 1, "resolved": 2, "closed": 3}
    rows.sort(key=lambda t: (rank[t.status], {"high": 0, "normal": 1, "low": 2}[t.priority], -t.id))
    return [_ticket_out(db, t) for t in rows]


@router.get("/tickets/{ticket_id}", response_model=TicketOut, summary="One ticket with its notes")
def get_ticket(ticket_id: int, db: Session = Depends(get_db)) -> TicketOut:
    return _ticket_out(db, _ticket(db, ticket_id), detail=True)


@router.post("/tickets", response_model=TicketOut, status_code=status.HTTP_201_CREATED, summary="Open a ticket")
def create_ticket(body: TicketIn, db: Session = Depends(get_db), user=Depends(require_user)) -> TicketOut:
    if body.customer_id and db.get(Customer, body.customer_id) is None:
        raise ApiError(404, "customer_not_found", "No such customer.")
    if body.order_id and db.get(Order, body.order_id) is None:
        raise ApiError(404, "order_not_found", "No such order.")
    t = Ticket(subject=body.subject.strip(), body=body.body, customer_id=body.customer_id, order_id=body.order_id, priority=body.priority)
    db.add(t)
    db.commit()
    return _ticket_out(db, t, detail=True)


@router.patch("/tickets/{ticket_id}", response_model=TicketOut, summary="Change status, priority or owner")
def change_ticket(ticket_id: int, body: TicketPatch, db: Session = Depends(get_db)) -> TicketOut:
    t = _ticket(db, ticket_id)
    sent = body.model_dump(exclude_unset=True)
    if body.status:
        service.move_ticket(t, body.status)
    if body.priority:
        t.priority = body.priority
    if "assigned_to" in sent:
        t.assigned_to = (body.assigned_to or "").strip() or None
    db.commit()
    return _ticket_out(db, t, detail=True)


@router.post("/tickets/{ticket_id}/notes", response_model=TicketOut, status_code=status.HTTP_201_CREATED, summary="Add an internal note")
def add_note(ticket_id: int, body: NoteIn, db: Session = Depends(get_db), user=Depends(require_user)) -> TicketOut:
    t = _ticket(db, ticket_id)
    service.add_note(db, t, body.text, _who(user))
    db.commit()
    return _ticket_out(db, t, detail=True)
