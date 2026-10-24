"""Auto Messenger, part 3: the "Customer videos" gallery, and the button that runs everything that is due."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import Customer, CustomerMedia, Order
from app.schemas.imports import CamelModel
from app.services import order_status, supabase_storage
from app.services.messaging import media as media_service

router = APIRouter(prefix="/messaging", tags=["messaging"])


class MediaOut(CamelModel):
    id: int
    customer_name: str
    order_number: str | None
    kind: Literal["image", "video"]
    mime_type: str | None
    size_bytes: int | None
    status: Literal["pending", "stored", "rejected", "failed"]
    error: str | None
    question_sent: bool
    share_answer: Literal["pending", "yes", "no"]
    usable_in_ads: bool
    received_at: datetime
    url: str | None                   # a link that expires after an hour


class UsableIn(CamelModel):
    usable: bool


class ProcessOut(CamelModel):
    stored: int
    rejected: int
    failed: int
    waiting: int


def _name(c: Customer | None) -> str:
    return " ".join(p for p in (c.first_name, c.last_name) if p) or c.external_id if c else "?"


def _out(db: Session, settings: Settings, m: CustomerMedia, customers: dict[int, Customer], orders: dict[int, Order]) -> MediaOut:
    order = orders.get(m.order_id) if m.order_id else None
    url = supabase_storage.signed_url_in(settings, settings.supabase_media_bucket, m.storage_path) if m.storage_path and m.status == "stored" else None
    return MediaOut(
        id=m.id, customer_name=_name(customers.get(m.customer_id)), order_number=order_status.order_number(order) if order else None,
        kind=m.kind, mime_type=m.mime_type, size_bytes=m.size_bytes, status=m.status, error=m.error, question_sent=m.question_sent,  # type: ignore[arg-type]
        share_answer=m.share_answer, usable_in_ads=m.usable_in_ads, received_at=m.received_at, url=url,  # type: ignore[arg-type]
    )


def _get(db: Session, media_id: int) -> CustomerMedia:
    media = db.get(CustomerMedia, media_id)
    if media is None:
        raise ApiError(404, "media_not_found", "That file was not found.")
    return media


@router.get("/media", response_model=list[MediaOut], summary="Customer videos and photos")
def list_media(
    show: str = Query(default="all", pattern="^(all|waiting|yes|no|usable|rejected)$"),
    limit: int = Query(default=60, ge=1, le=200), db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> list[MediaOut]:
    query = select(CustomerMedia).order_by(CustomerMedia.id.desc()).limit(limit)
    if show == "waiting":
        query = query.where(CustomerMedia.status == "stored", CustomerMedia.share_answer == "pending")
    elif show in ("yes", "no"):
        query = query.where(CustomerMedia.share_answer == show, CustomerMedia.status == "stored")
    elif show == "usable":
        query = query.where(CustomerMedia.usable_in_ads.is_(True))
    elif show == "rejected":
        query = query.where(CustomerMedia.status.in_(("rejected", "failed")))
    rows = list(db.scalars(query))
    customers = {c.id: c for c in db.scalars(select(Customer).where(Customer.id.in_({m.customer_id for m in rows})))} if rows else {}
    orders = {o.id: o for o in db.scalars(select(Order).where(Order.id.in_({m.order_id for m in rows if m.order_id})))} if rows else {}
    return [_out(db, settings, m, customers, orders) for m in rows]


@router.post("/media/{media_id}/usable", response_model=MediaOut, summary="Mark a file usable (or not) in ads")
def set_usable(media_id: int, body: UsableIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> MediaOut:
    """Allowed only after the customer answered YES to "may we share it?"."""
    media = _get(db, media_id)
    media_service.set_usable(media, body.usable)
    db.commit()
    return _out(db, settings, media, {c.id: c for c in db.scalars(select(Customer).where(Customer.id == media.customer_id))}, {})


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a file (the stored copy too)")
def delete_media(media_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> Response:
    media = _get(db, media_id)
    path = media.storage_path
    db.delete(media)
    db.commit()
    if path:
        supabase_storage.delete_object(settings, settings.supabase_media_bucket, path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/media/process", response_model=ProcessOut, summary="Download and store the files that are waiting")
def process_media(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> ProcessOut:
    counts = media_service.process_pending_media(db, settings, limit=5)
    db.commit()
    return ProcessOut(**counts)


@router.post("/run-due", summary="Run everything that is due now (the same as the scheduler)")
def run_due_now(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    from app.services.messaging import scheduler

    return scheduler.run_due(db, settings)
