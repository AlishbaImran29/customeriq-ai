"""Which delivered COD parcels have the courier's payments paid for? First in, first out (FIFO).

Plain rules, so a shopkeeper can check them by hand, and no machine learning:
1. Each courier is matched separately. A parcel is "owed" once it is delivered; it owes its COD amount.
2. Payments are used in date order. A payment first goes to the orders it names (`order_refs`), if any,
   and what is left goes to the OLDEST unpaid delivered parcel, then the next oldest, and so on.
3. A payment cannot pay a parcel that was delivered after the payment date.
4. A parcel is paid (fully covered), partly paid (some covered) or pending (nothing yet).
5. The day a parcel became fully covered is the payment date that finished it: that gives "days to pay".
6. Money left over after every owed parcel is covered is reported as credit, never lost.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

PAID, PARTLY, PENDING = "paid", "partly_paid", "pending"


@dataclass
class Parcel:
    key: int                        # any unique id (the shipment id)
    courier: str
    delivered_on: date
    amount: Decimal                 # the COD amount the courier collected
    order_ref: str | None = None    # the order's own id, so a payment can name it
    paid: Decimal = Decimal("0")
    settled_on: date | None = None  # the payment date that fully covered it

    @property
    def due(self) -> Decimal:
        return self.amount - self.paid

    @property
    def status(self) -> str:
        if self.paid >= self.amount:
            return PAID
        return PARTLY if self.paid > 0 else PENDING

    @property
    def days_to_pay(self) -> int | None:
        return (self.settled_on - self.delivered_on).days if self.settled_on else None


@dataclass
class Payment:
    key: int
    courier: str
    paid_on: date
    amount: Decimal
    order_refs: list[str] = field(default_factory=list)


def _pay(parcel: Parcel, amount: Decimal, when: date) -> Decimal:
    """Pay up to the parcel's due; return what was used."""
    used = min(amount, parcel.due)
    if used <= 0:
        return Decimal("0")
    parcel.paid += used
    if parcel.paid >= parcel.amount:
        parcel.settled_on = when
    return used


def match(parcels: list[Parcel], payments: list[Payment]) -> dict[str, Decimal]:
    """Fill in `paid` / `settled_on` on the parcels (in place). Returns the unused credit per courier."""
    credit: dict[str, Decimal] = {}
    by_courier: dict[str, list[Parcel]] = {}
    for parcel in parcels:
        by_courier.setdefault(parcel.courier, []).append(parcel)
    for items in by_courier.values():
        items.sort(key=lambda p: (p.delivered_on, p.key))        # oldest first
    for payment in sorted(payments, key=lambda p: (p.paid_on, p.key)):
        items = by_courier.get(payment.courier, [])
        left = payment.amount
        named = {ref.strip() for ref in payment.order_refs if ref.strip()}
        # The orders this payment names come first, then the oldest.
        for parcel in [p for p in items if p.order_ref in named] + [p for p in items if p.order_ref not in named]:
            if left <= 0:
                break
            if parcel.delivered_on <= payment.paid_on:
                left -= _pay(parcel, left, payment.paid_on)
        if left > 0:
            credit[payment.courier] = credit.get(payment.courier, Decimal("0")) + left
    return credit
