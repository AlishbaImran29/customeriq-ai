"""The places in the app that tell the automation engine "this just happened". Each one is a single line at the call site.

They import the engine inside the function (the engine uses the order and messaging code that calls these hooks) and
`emit` itself never raises, so none of these can break the order, status or message that triggered them.
"""

from sqlalchemy.orm import Session

from app.core.config import get_settings


def _emit(db: Session, trigger: str, payload: dict, key: str) -> None:
    from app.services.workflows import engine

    engine.emit(db, get_settings(), trigger, payload, key)


def order_created(db: Session, order, new_customer: bool = False) -> None:
    if new_customer:
        _emit(db, "customer_created", {"customer_id": order.customer_id}, f"customer_created:{order.customer_id}")
    _emit(db, "order_created", {"order_id": order.id, "customer_id": order.customer_id}, f"order_created:{order.id}")


def order_status_changed(db: Session, order, status: str) -> None:
    _emit(db, "order_status_changed", {"order_id": order.id, "customer_id": order.customer_id, "status": status}, f"order_status:{order.id}:{status}")


def message_received(db: Session, customer_id: int, text: str | None, provider_id: str) -> None:
    _emit(db, "message_received", {"customer_id": customer_id, "text": text or ""}, f"message_received:{provider_id}")


def stock_changed(db: Session, item, available_before: int, movement_id: int) -> None:
    """Fires once each time the available stock falls from above the warning level to at or below it."""
    if item.status == "active" and available_before > item.reorder_threshold >= item.stock - item.reserved:
        _emit(db, "stock_below_threshold", {"item_id": item.id}, f"stock_low:{item.id}:{movement_id}")
