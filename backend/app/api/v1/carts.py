"""Abandoned carts: the list and the honest numbers."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Customer
from app.models.abandoned_cart import AbandonedCart
from app.schemas.imports import CamelModel
from app.services import data_rules

router = APIRouter(prefix="/carts", tags=["carts"])


class CartOut(CamelModel):
    id: int
    customer_name: str | None
    items: str | None
    total: float | None
    currency: str | None
    status: str
    reminders_sent: int
    last_reminder_at: datetime | None
    checkout_updated_at: datetime
    recovered_at: datetime | None


@router.get("", response_model=list[CartOut], summary="Abandoned carts, newest first")
def list_carts(status: str | None = Query(None, pattern="^(open|recovered|expired|no_contact)$"), db: Session = Depends(get_db)) -> list[CartOut]:
    query = select(AbandonedCart, Customer).outerjoin(Customer, Customer.id == AbandonedCart.customer_id).order_by(AbandonedCart.checkout_updated_at.desc()).limit(200)
    if status:
        query = query.where(AbandonedCart.status == status)
    return [
        CartOut(
            id=c.id, customer_name=(" ".join(p for p in (u.first_name, u.last_name) if p) or u.external_id) if u else None, items=c.items,
            total=float(c.total) if c.total is not None else None, currency=c.currency, status=c.status, reminders_sent=c.reminders_sent,
            last_reminder_at=c.last_reminder_at, checkout_updated_at=c.checkout_updated_at, recovered_at=c.recovered_at,
        )
        for c, u in db.execute(query)
    ]


@router.get("/summary", summary="Counts by status, and the recovery rate only when there are enough carts to mean something")
def summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    counts = dict(db.execute(select(AbandonedCart.status, func.count()).group_by(AbandonedCart.status)).all())
    reminded = db.scalar(select(func.count()).select_from(AbandonedCart).where(AbandonedCart.reminders_sent > 0)) or 0
    recovered_after = db.scalar(select(func.count()).select_from(AbandonedCart).where(AbandonedCart.reminders_sent > 0, AbandonedCart.status == "recovered")) or 0
    enough = data_rules.enough(reminded)
    return {
        "counts": {s: int(counts.get(s, 0)) for s in ("open", "recovered", "expired", "no_contact")},
        "reminded": int(reminded), "recoveredAfterReminder": int(recovered_after),
        "recoveryRate": round(recovered_after / reminded, 4) if enough else None, "minGroupCount": data_rules.MIN_GROUP_COUNT,
        "note": "Some of these shoppers would have come back without a reminder, so this is not the effect of the reminder.",
    }
