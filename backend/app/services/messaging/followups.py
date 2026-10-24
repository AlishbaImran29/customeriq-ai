"""Messages that follow a delivery on a schedule (Auto Messenger part 3): the review request.

REVIEW REQUEST: 3 days after an order was delivered, if it was not returned, the customer is sent a message with the
seller's review link. It runs whenever the scheduler (or the "run due messages" button) calls `run_review_requests`.
Rules: only orders delivered between 3 and 14 days ago (an old order is not chased); never for a returned order; the
event key "order:<id>:review_request" means each order is asked at most once; and with no review link in the settings
nothing is created at all, so the requests go out as soon as the link is added.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Customer, Message, Order, OrderStatusHistory
from app.services import order_status
from app.services.messaging import service
from app.services.messaging.settings_store import get_row

REVIEW_DELAY_DAYS = 3
REVIEW_WINDOW_DAYS = 14                         # an order delivered longer ago than this is not asked any more


def run_review_requests(db: Session, settings: Settings, now: datetime | None = None, limit: int = 100) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    row = get_row(db)
    counts = {"checked": 0, "asked": 0, "no_link": 0}
    if not (row.review_url or "").strip():
        counts["no_link"] = 1                    # reported so the page can say "add your review link"
        return counts
    newest = (
        select(OrderStatusHistory.order_id, func.max(OrderStatusHistory.at).label("at"), func.max(OrderStatusHistory.id).label("id"))
        .group_by(OrderStatusHistory.order_id).subquery()
    )
    latest = (
        select(OrderStatusHistory.order_id, OrderStatusHistory.status, OrderStatusHistory.at)
        .join(newest, (OrderStatusHistory.order_id == newest.c.order_id) & (OrderStatusHistory.id == newest.c.id)).subquery()
    )
    due = db.execute(
        select(Order, latest.c.at)
        .join(latest, latest.c.order_id == Order.id)
        .where(latest.c.status == "delivered", latest.c.at <= now - timedelta(days=REVIEW_DELAY_DAYS), latest.c.at >= now - timedelta(days=REVIEW_WINDOW_DAYS))
        .order_by(latest.c.at).limit(limit)
    ).all()
    for order, _ in due:
        counts["checked"] += 1
        if order.outcome == "returned":
            continue
        key = f"{order.customer_id}:whatsapp:order:{order.id}:review_request"
        if db.scalar(select(Message.id).where(Message.idempotency_key == key)) is not None:
            continue
        customer = db.get(Customer, order.customer_id)
        if customer is None:
            continue
        language = order_status.customer_language(customer, row.default_language)
        template = order_status.pick_template(db, "review_request", "whatsapp", language, row.default_language)
        if template is None:
            continue
        extra = order_status.order_variables(db, order, customer, "delivered", template.language, None, None)
        message = service.send_message(
            db, settings, customer, "whatsapp", template, service.customer_variables(customer, row, template.language, extra),
            event_key=f"order:{order.id}:review_request", event="review_request", order_id=order.id, now=now,
        )
        counts["asked"] += int(message.status in ("sent", "queued"))
    return counts
