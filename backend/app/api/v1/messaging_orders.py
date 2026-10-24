"""Auto Messenger, part 2: the default templates, and the order status board (change a status by hand)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import Customer, Message, MessageTemplate, Order, OrderStatusHistory
from app.schemas.messaging import MessageOut
from app.schemas.messaging_orders import OrderRowOut, SeedIn, SeedOut, StatusEventOut, StatusIn, StatusResultOut, TimelineOut
from app.services import order_status
from app.services.messaging import defaults

router = APIRouter(prefix="/messaging", tags=["messaging"])


def _name(c: Customer) -> str:
    return " ".join(p for p in (c.first_name, c.last_name) if p) or c.external_id


def _like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def message_out(m: Message, names: dict[int, str], templates: dict[int, str]) -> MessageOut:
    return MessageOut(
        id=m.id, customer_id=m.customer_id, customer_name=names.get(m.customer_id, "?"), channel=m.channel, category=m.category,  # type: ignore[arg-type]
        subject=m.subject, text=m.rendered_text, status=m.status, error=m.error, attempts=m.attempts, dry_run=m.dry_run,  # type: ignore[arg-type]
        template_name=templates.get(m.template_id) if m.template_id else None, campaign_id=m.campaign_id, journey_id=m.journey_id,
        order_id=m.order_id, queued_at=m.queued_at, sent_at=m.sent_at, next_attempt_at=m.next_attempt_at,
    )


def _message_rows(db: Session, messages: list[Message]) -> list[MessageOut]:
    names = {c.id: _name(c) for c in db.scalars(select(Customer).where(Customer.id.in_({m.customer_id for m in messages})))} if messages else {}
    templates = {t.id: t.name for t in db.scalars(select(MessageTemplate).where(MessageTemplate.id.in_({m.template_id for m in messages if m.template_id})))} if messages else {}
    return [message_out(m, names, templates) for m in messages]


@router.post("/templates/seed-defaults", response_model=SeedOut, summary="Add the ready-made Urdu and English templates (not approved)")
def seed_default_templates(body: SeedIn, db: Session = Depends(get_db)) -> SeedOut:
    """Adds only the ones that are missing, and never overwrites one you changed. Every one starts UNAPPROVED."""
    groups = body.groups or ["orders", "followups"]
    extra: list[dict] = []
    if "journeys" in groups:
        from app.services.messaging import journey_defaults

        extra = journey_defaults.journey_templates()
    added = defaults.seed_defaults(db, [g for g in groups if g in defaults.DEFAULT_GROUPS], extra)
    db.commit()
    return SeedOut(added=added)


@router.get("/orders", response_model=list[OrderRowOut], summary="Recent orders with their current status")
def order_board(search: str | None = Query(default=None, max_length=80), limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)) -> list[OrderRowOut]:
    query = select(Order, Customer).join(Customer, Customer.id == Order.customer_id).order_by(Order.order_date.desc(), Order.id.desc()).limit(limit)
    if search and search.strip():
        pattern = f"%{_like(search.strip())}%"
        query = query.where(or_(*(col.ilike(pattern, escape="\\") for col in (Order.external_id, Order.products, Customer.first_name, Customer.last_name, Customer.phone_normalised, Customer.phone))))
    rows = db.execute(query).all()
    ids = [o.id for o, _ in rows]
    latest: dict[int, OrderStatusHistory] = {}
    counts: dict[int, int] = {}
    if ids:
        for h in db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id.in_(ids)).order_by(OrderStatusHistory.at, OrderStatusHistory.id)):
            latest[h.order_id] = h                                  # the last one read is the newest
        counts = {oid: n for oid, n in db.execute(select(Message.order_id, func.count()).where(Message.order_id.in_(ids)).group_by(Message.order_id))}
    return [
        OrderRowOut(
            id=o.id, order_number=order_status.order_number(o), customer_id=c.id, customer_name=_name(c), phone=c.phone_normalised or c.phone,
            amount=float(o.order_value), payment_type=o.payment_type, products=o.products,
            status=latest[o.id].status if o.id in latest else None, status_at=latest[o.id].at if o.id in latest else None,  # type: ignore[arg-type]
            messages=int(counts.get(o.id, 0)),
        ) for o, c in rows
    ]


def _order(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise ApiError(404, "order_not_found", "That order was not found.")
    return order


@router.get("/orders/{order_id}/timeline", response_model=TimelineOut, summary="The status history and messages of one order")
def order_timeline(order_id: int, db: Session = Depends(get_db)) -> TimelineOut:
    order = _order(db, order_id)
    customer = db.get(Customer, order.customer_id)
    events = db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id == order_id).order_by(OrderStatusHistory.at, OrderStatusHistory.id))
    messages = list(db.scalars(select(Message).where(Message.order_id == order_id).order_by(Message.id)))
    return TimelineOut(
        order_number=order_status.order_number(order), customer_name=_name(customer) if customer else "?",
        events=[StatusEventOut(status=e.status, at=e.at, source=e.source, courier=e.courier, tracking_number=e.tracking_number, note=e.note) for e in events],  # type: ignore[arg-type]
        messages=_message_rows(db, messages),
    )


@router.post("/orders/{order_id}/status", response_model=StatusResultOut, summary="Change an order's status by hand")
def change_order_status(order_id: int, body: StatusIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> StatusResultOut:
    """Records the status. If it is a step forward and fresh, the customer is messaged on the channels they agreed to
    (the checks in services/messaging/service.py still apply, so a customer without consent gets nothing)."""
    order = _order(db, order_id)
    change = order_status.record_status(
        db, settings, order, body.status, source="manual", courier=(body.courier or "").strip() or None,
        tracking=(body.tracking_number or "").strip() or None, note=(body.note or "").strip() or None, notify=body.notify,
    )
    db.commit()
    return StatusResultOut(recorded=change.recorded, announced=change.announced, reason=change.reason, messages=_message_rows(db, change.messages))
