"""Vendor Book helpers (step 2): phone numbers, which quote is cheapest or fastest, and a vendor's return rate."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import LaunchProduct, LaunchProject
from app.services import data_rules
from app.services.launch_results import orders_for_project
from app.services.phone import normalise_pk_phone


def clean_phone(text: str | None) -> str | None:
    """+92XXXXXXXXXX or None when blank. A number that cannot be read is refused, never guessed."""
    if text is None or not text.strip():
        return None
    number = normalise_pk_phone(text)
    if number is None:
        raise ApiError(422, "invalid_phone", "That does not look like a Pakistani mobile number. Write it like 0300 1234567 or +92 300 1234567.", {"field": "whatsappPhone"})
    return number


def best_quotes(quotes: list) -> tuple[set[int], set[int]]:
    """(ids of the cheapest quotes, ids of the fastest quotes). Ties are all marked; with a single quote nothing is marked,
    because "cheapest of one" says nothing."""
    if len(quotes) < 2:
        return set(), set()
    low = min(float(q.unit_price) for q in quotes)
    cheapest = {q.id for q in quotes if float(q.unit_price) == low}
    timed = [q for q in quotes if q.delivery_days is not None]
    fastest = set()
    if len(timed) >= 2:
        quick = min(q.delivery_days for q in timed)
        fastest = {q.id for q in timed if q.delivery_days == quick}
    return cheapest, fastest


@dataclass
class VendorQuality:
    closed_orders: int = 0
    return_rate: float | None = None
    needed: int = 0
    projects: int = 0                      # launched projects that used this vendor


def vendor_quality(db: Session, vendor_id: int) -> VendorQuality:
    """The return rate of orders for products this vendor supplied.

    "Supplied" means the seller chose this vendor on a launch project and linked that project to product names,
    so the orders come from step 6. Only orders whose outcome came from courier data count (a real delivered or
    returned result), and only with at least MIN_GROUP_COUNT of them; otherwise "Not enough data yet".
    """
    projects = list(db.scalars(select(LaunchProject).where(LaunchProject.chosen_vendor_id == vendor_id, LaunchProject.launched_on.is_not(None))))
    quality = VendorQuality(projects=len(projects))
    returned = 0
    for project in projects:
        keys = {p.name_key for p in db.scalars(select(LaunchProduct).where(LaunchProduct.launch_project_id == project.id))}
        for order in orders_for_project(db, project, keys, courier_only=True):
            if order.outcome in ("delivered", "returned"):
                quality.closed_orders += 1
                returned += order.outcome == "returned"
    quality.needed = data_rules.more_needed(quality.closed_orders)
    if data_rules.enough(quality.closed_orders):
        quality.return_rate = returned / quality.closed_orders
    return quality
