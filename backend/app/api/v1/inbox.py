"""Support inbox: conversations, a thread, typed replies, notes, assignment, FAQ answers, and the response-time metric."""

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_user
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import Customer, IncomingMessage, Message, MessageTemplate
from app.models.inbox import Conversation, FaqEntry, InboxNote
from app.schemas.imports import CamelModel
from app.services import inbox as service

router = APIRouter(prefix="/inbox", tags=["inbox"])


class ConversationOut(CamelModel):
    customer_id: int
    customer_name: str
    phone: str | None
    last_text: str | None
    last_at: datetime
    last_from: Literal["customer", "us"]
    unread: int
    status: Literal["open", "closed"]
    assigned_to: str | None
    intent: str


class ThreadItem(CamelModel):
    at: datetime
    direction: Literal["in", "out"]
    text: str | None
    kind: str
    status: str | None = None
    error: str | None = None


class NoteOut(CamelModel):
    id: int
    author: str | None
    body: str
    at: datetime


class SuggestionOut(CamelModel):
    intent: str
    escalate: bool
    reason: str | None
    draft: str | None
    sources: list[str]
    label: str = "Drafted from your records (not AI). Read it before you send."


class ThreadOut(CamelModel):
    customer_id: int
    customer_name: str
    phone: str | None
    status: Literal["open", "closed"]
    assigned_to: str | None
    session_open: bool
    items: list[ThreadItem]
    notes: list[NoteOut]
    suggestion: SuggestionOut | None


class ReplyIn(CamelModel):
    text: str = Field(min_length=1, max_length=1000)


class NoteIn(CamelModel):
    body: str = Field(min_length=1, max_length=2000)


class AssignIn(CamelModel):
    assigned_to: str | None = Field(default=None, max_length=320)
    status: Literal["open", "closed"] | None = None


class FaqIn(CamelModel):
    title: str = Field(min_length=1, max_length=120)
    keywords: str = Field(min_length=1, max_length=300)
    answer: str = Field(min_length=1, max_length=2000)


class FaqOut(FaqIn):
    id: int


def _name(c: Customer) -> str:
    return " ".join(p for p in (c.first_name, c.last_name) if p) or c.external_id


def _customer(db: Session, customer_id: int) -> Customer:
    c = db.get(Customer, customer_id)
    if c is None:
        raise ApiError(404, "customer_not_found", "No such customer.")
    return c


@router.get("", response_model=list[ConversationOut], summary="Conversations, the ones waiting for you first")
def conversations(state: Literal["open", "closed"] | None = Query(None), db: Session = Depends(get_db)) -> list[ConversationOut]:
    last_in = (
        select(IncomingMessage.customer_id, func.max(IncomingMessage.received_at).label("at")).where(IncomingMessage.customer_id.is_not(None)).group_by(IncomingMessage.customer_id).subquery()
    )
    out: list[ConversationOut] = []
    for customer_id, at in db.execute(select(last_in.c.customer_id, last_in.c.at).order_by(last_in.c.at.desc()).limit(200)):
        c = db.get(Customer, customer_id)
        convo = db.scalar(select(Conversation).where(Conversation.customer_id == customer_id))
        if state and (convo.status if convo else "open") != state:
            continue
        latest = db.scalar(select(IncomingMessage).where(IncomingMessage.customer_id == customer_id).order_by(IncomingMessage.received_at.desc()).limit(1))
        last_read = convo.last_read_at if convo else None
        unread = db.scalar(select(func.count()).select_from(IncomingMessage).where(IncomingMessage.customer_id == customer_id, *( [IncomingMessage.received_at > last_read] if last_read else []))) or 0
        out.append(ConversationOut(
            customer_id=customer_id, customer_name=_name(c), phone=c.phone, last_text=latest.body if latest else None, last_at=at, last_from="customer", unread=int(unread),
            status=convo.status if convo else "open", assigned_to=convo.assigned_to if convo else None, intent=service.classify(latest.body if latest else None),  # type: ignore[arg-type]
        ))
    out.sort(key=lambda r: (r.unread == 0, -r.last_at.timestamp()))
    return out


@router.get("/metrics", summary="How fast you answer (only when there are enough questions)")
def metrics(db: Session = Depends(get_db)) -> dict[str, Any]:
    average, measured = service.response_minutes(db)
    return {"averageResponseMinutes": round(average, 1) if average is not None else None, "questionsMeasured": measured, "days": 30, "note": "Counts only replies you typed; automatic messages do not count."}


@router.get("/{customer_id}", response_model=ThreadOut, summary="One conversation, with a drafted reply when the records can answer")
def thread(customer_id: int, db: Session = Depends(get_db)) -> ThreadOut:
    c = _customer(db, customer_id)
    convo = service.conversation(db, customer_id)
    incoming = list(db.scalars(select(IncomingMessage).where(IncomingMessage.customer_id == customer_id).order_by(IncomingMessage.received_at.desc()).limit(100)))
    outgoing = list(db.execute(select(Message, MessageTemplate.event).outerjoin(MessageTemplate, MessageTemplate.id == Message.template_id).where(Message.customer_id == customer_id, Message.channel == "whatsapp").order_by(Message.queued_at.desc()).limit(100)))
    items = [ThreadItem(at=m.received_at, direction="in", text=m.body, kind=m.message_type) for m in incoming]
    items += [ThreadItem(at=m.sent_at or m.queued_at, direction="out", text=m.rendered_text, kind="typed" if event == "manual_reply" else "automatic", status=m.status, error=m.error) for m, event in outgoing]
    items.sort(key=lambda i: i.at)
    notes = [NoteOut(id=n.id, author=n.author, body=n.body, at=n.at) for n in db.scalars(select(InboxNote).where(InboxNote.customer_id == customer_id).order_by(InboxNote.id))]
    latest_text = incoming[0].body if incoming else None
    suggestion = None
    if incoming and (not outgoing or incoming[0].received_at >= max((m.sent_at or m.queued_at) for m, _ in outgoing)):
        s = service.suggest(db, c, latest_text)
        suggestion = SuggestionOut(intent=s.intent, escalate=s.escalate, reason=s.reason, draft=s.draft, sources=s.sources)
    service.mark_read(db, customer_id)
    db.commit()
    return ThreadOut(
        customer_id=customer_id, customer_name=_name(c), phone=c.phone, status=convo.status, assigned_to=convo.assigned_to,  # type: ignore[arg-type]
        session_open=service.service.has_open_session(db, customer_id, datetime.now(timezone.utc)), items=items, notes=notes, suggestion=suggestion,
    )


@router.post("/{customer_id}/reply", response_model=ThreadItem, status_code=status.HTTP_201_CREATED, summary="Send a typed WhatsApp reply")
def send_reply(customer_id: int, body: ReplyIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> ThreadItem:
    message = service.reply(db, settings, _customer(db, customer_id), body.text)
    db.commit()
    return ThreadItem(at=message.sent_at or message.queued_at, direction="out", text=message.rendered_text, kind="typed", status=message.status, error=message.error)


@router.post("/{customer_id}/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED, summary="Add an internal note")
def add_note(customer_id: int, body: NoteIn, db: Session = Depends(get_db), user=Depends(require_user)) -> InboxNote:
    _customer(db, customer_id)
    note = InboxNote(customer_id=customer_id, author=getattr(user, "email", None), body=body.body.strip())
    db.add(note)
    db.commit()
    return note


@router.patch("/{customer_id}", summary="Assign the conversation or close / reopen it")
def assign(customer_id: int, body: AssignIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    _customer(db, customer_id)
    convo = service.conversation(db, customer_id)
    sent = body.model_dump(exclude_unset=True)
    if "assigned_to" in sent:
        convo.assigned_to = (body.assigned_to or "").strip() or None
    if body.status:
        convo.status = body.status
    db.commit()
    return {"status": convo.status, "assignedTo": convo.assigned_to}


@router.get("/faq/list", response_model=list[FaqOut], summary="Your own ready answers")
def faq_list(db: Session = Depends(get_db)) -> list[FaqEntry]:
    return list(db.scalars(select(FaqEntry).order_by(FaqEntry.id)))


@router.post("/faq/list", response_model=FaqOut, status_code=status.HTTP_201_CREATED, summary="Add a ready answer")
def faq_add(body: FaqIn, db: Session = Depends(get_db)) -> FaqEntry:
    entry = FaqEntry(title=body.title.strip(), keywords=body.keywords.strip(), answer=body.answer.strip())
    db.add(entry)
    db.commit()
    return entry


@router.delete("/faq/{faq_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a ready answer (owner only)")
def faq_delete(faq_id: int, db: Session = Depends(get_db)) -> None:
    entry = db.get(FaqEntry, faq_id)
    if entry is None:
        raise ApiError(404, "faq_not_found", "No such answer.")
    db.delete(entry)
    db.commit()
