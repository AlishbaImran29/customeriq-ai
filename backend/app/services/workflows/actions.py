"""What each action type does. `perform` does it; `describe` says what it WOULD do without doing anything (the dry run).

An action never decides anything about the order that started the workflow: if one fails it fails alone, is retried, and is
logged. Only `update_order_status` changes an order, and only along a valid forward step.
"""

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Customer, Order
from app.models.workflow import Task
from app.services import customer_records, order_status
from app.services.messaging import service
from app.services.messaging.settings_store import get_row

WEBHOOK_TIMEOUT_SECONDS = 5


class NonRetryable(Exception):
    """A failure that trying again cannot fix (a missing template, a web address that is not approved...)."""


def _customer(db: Session, payload: dict) -> Customer:
    customer = db.get(Customer, payload.get("customer_id") or 0)
    if customer is None:
        raise NonRetryable("no_customer")
    return customer


def _order(db: Session, payload: dict) -> Order:
    order = db.get(Order, payload.get("order_id") or 0)
    if order is None:
        raise NonRetryable("no_order")
    return order


def _template(db: Session, customer: Customer, params: dict):
    row = get_row(db)
    language = order_status.customer_language(customer, row.default_language)
    template = order_status.pick_template(db, params["event"], params["channel"], language, row.default_language)
    if template is None:
        raise NonRetryable("no_template")
    return row, template


def allowed_webhooks(settings: Settings) -> set[str]:
    return {u.strip() for u in (settings.workflow_webhook_urls or "").split(",") if u.strip().startswith("https://")}


def describe(db: Session, settings: Settings, action: dict, payload: dict) -> str:
    """One plain sentence about what this step would do now. Touches nothing."""
    kind, p = action["type"], action.get("params") or {}
    try:
        if kind == "send_message":
            customer = _customer(db, payload)
            row, template = _template(db, customer, p)
            from app.services.messaging import consent

            state = consent.consent_state(db, customer.id, p["channel"])
            if not template.approved_by_seller:
                return f"Would try to send '{template.name}', but it is not approved yet, so nothing would be sent."
            if state != "opted_in":
                return f"Would try to send '{template.name}', but the customer has not agreed to {p['channel']}, so nothing would be sent."
            return f"Would send '{template.name}' on {p['channel']}."
        if kind == "add_tag":
            return f"Would add the tag '{p['tag']}' to {_customer(db, payload).first_name or 'the customer'}."
        if kind == "remove_tag":
            return f"Would remove the tag '{p['tag']}'."
        if kind == "create_task":
            return f"Would add the to-do '{p['title']}'."
        if kind == "notify":
            return f"Would show the notification '{p['title']}'."
        if kind == "update_order_status":
            order = _order(db, payload)
            current = order_status.latest_status(db, order.id)
            if current is not None and current.status == p["status"]:
                return f"The order is already '{p['status']}': nothing would change."
            if not order_status.is_forward(current.status if current else None, p["status"]):
                return f"Would be refused: the order cannot go from '{current.status}' back to '{p['status']}'."
            return f"Would change the order to '{p['status']}'."
        if kind == "call_webhook":
            return "Would call the approved web address." if p["url"] in allowed_webhooks(settings) else "Would be refused: this web address is not in the approved list (WORKFLOW_WEBHOOK_URLS)."
    except NonRetryable as exc:
        return f"Would fail: {exc}."
    return "Unknown action."


def perform(db: Session, settings: Settings, action: dict, payload: dict, *, run_id: int, step: int, now: datetime) -> dict[str, Any]:
    """Do the action. Returns a small JSON-able result for the log. Raises NonRetryable or any other error (which is retried)."""
    kind, p = action["type"], action.get("params") or {}
    if kind == "send_message":
        customer = _customer(db, payload)
        row, template = _template(db, customer, p)
        order = db.get(Order, payload["order_id"]) if payload.get("order_id") else None
        extra = order_status.order_variables(db, order, customer, payload.get("status") or "confirmed", template.language, None, None) if order else None
        values = service.customer_variables(customer, row, template.language, extra)
        message = service.send_message(db, settings, customer, p["channel"], template, values, event_key=f"wf:{run_id}:{step}", event=template.event,
                                       order_id=order.id if order else None, now=now)
        return {"message_id": message.id, "status": message.status, "reason": message.error}
    if kind in ("add_tag", "remove_tag"):
        customer = _customer(db, payload)
        tags = list(customer.tags or [])
        wanted = p["tag"].strip()
        if kind == "add_tag":
            tags.append(wanted)
        else:
            tags = [t for t in tags if t.casefold() != wanted.casefold()]
        customer.tags = customer_records.clean_tags(tags)
        customer_records.audit(db, "edit", customer, fields=["tags"], by="workflow")
        return {"tags": customer.tags}
    if kind in ("create_task", "notify"):
        customer_id = payload.get("customer_id")
        due = now + timedelta(hours=int(p.get("dueInHours", 24))) if kind == "create_task" else None
        task = Task(kind="task" if kind == "create_task" else "notification", title=p["title"].strip()[:200], detail=(p.get("detail") or None), customer_id=customer_id, run_id=run_id, due_at=due)
        db.add(task)
        db.flush()
        return {"task_id": task.id}
    if kind == "update_order_status":
        order = _order(db, payload)
        current = order_status.latest_status(db, order.id)
        if current is not None and current.status == p["status"]:
            return {"changed": False, "reason": "already_that_status"}
        if not order_status.is_forward(current.status if current else None, p["status"]):
            raise NonRetryable("invalid_transition")
        change = order_status.record_status(db, settings, order, p["status"], source="system", now=now, at=now)
        return {"changed": change.recorded, "messages": len(change.messages)}
    if kind == "call_webhook":
        url = p["url"]
        if url not in allowed_webhooks(settings):
            raise NonRetryable("webhook_not_approved")
        return _post(url, {"workflow_run": run_id, "step": step, "order_id": payload.get("order_id"), "customer_id": payload.get("customer_id")})
    raise NonRetryable("unknown_action")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):          # an approved address may not send us somewhere else
        return None


def _post(url: str, body: dict) -> dict:
    if urlsplit(url).scheme != "https":
        raise NonRetryable("webhook_not_https")
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=WEBHOOK_TIMEOUT_SECONDS) as response:   # noqa: S310 (https only, approved list)
            return {"http_status": response.status}
    except urllib.error.HTTPError as exc:
        if 400 <= exc.code < 500 and exc.code != 429:
            raise NonRetryable(f"webhook_http_{exc.code}") from exc
        raise
