"""Results of the Auto Messenger (Auto Messenger part 6).

WHAT IS COUNTED, per template, campaign and journey
    sent        the provider accepted the message           delivered / read / replied   what WhatsApp and the customer did
    failed      it could not be sent                        skipped                      it was never sent (no consent, cap...)
    opt-outs    customers who stopped within 7 days after one of these messages (blamed on the last message before it)
    orders / revenue within 7 days   orders the same customer placed in the 7 days after a message of this group
                                      (each order counted once per group). THIS IS NOT PROOF the message caused them:
                                      the customer might have ordered anyway. That is what the holdout comparison is for.

MESSAGED GROUP VS HOLDOUT (journeys only)
    Every journey keeps a random 10% of its customers aside (the holdout): they are enrolled but never messaged. Both
    groups are compared over the 7 days from the day the first message was (or would have been) due, counting only
    customers whose 7 days are over. The comparison is "intention to treat": everyone who was meant to be messaged
    counts as messaged, even if a message was later skipped, so the comparison cannot be flattered.
    The difference comes with a 95% confidence interval. If either group has fewer than MIN_MESSAGING_GROUP customers
    (default 30), there is no result, only "Not enough data yet" (project rule 2). If the interval includes 0 the page says
    the difference could be chance.

COST is the number of WhatsApp messages sent per category times the per-message price the SELLER typed in the settings.
No price is built in: Meta changes its prices, and a made-up price would be an invented number.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import sqrt

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.models import Campaign, ConsentEvent, Journey, JourneyEnrollment, Message, MessageTemplate, Order
from app.services.messaging.settings_store import get_row

MIN_MESSAGING_GROUP = 30                  # customers needed in EACH group before a comparison is shown
WINDOW_DAYS = 7
Z95 = 1.96


@dataclass
class GroupStats:
    key: int | None
    name: str
    channel_mix: dict[str, int]
    sent: int = 0
    delivered: int = 0
    read: int = 0
    replied: int = 0
    failed: int = 0
    skipped: int = 0
    opt_outs: int = 0
    orders: int = 0
    revenue: float = 0.0
    whatsapp_utility: int = 0
    whatsapp_marketing: int = 0


@dataclass
class Comparison:
    enough: bool
    messaged: int
    holdout: int
    needed: int                           # more customers needed in the smaller group
    messaged_rate: float | None = None
    holdout_rate: float | None = None
    difference: float | None = None       # messaged minus holdout, in percentage points / 100
    low: float | None = None              # 95% interval of the difference
    high: float | None = None
    could_be_chance: bool | None = None
    messaged_revenue: float | None = None # average revenue per customer in the 7 days
    holdout_revenue: float | None = None
    reason: str | None = None             # no_real_messages / too_new


def two_proportion_interval(orders_a: int, n_a: int, orders_b: int, n_b: int) -> tuple[float, float, float]:
    """(difference a - b, low, high): the gap between two shares and its 95% confidence interval (normal approximation)."""
    pa, pb = orders_a / n_a, orders_b / n_b
    spread = Z95 * sqrt(pa * (1 - pa) / n_a + pb * (1 - pb) / n_b)
    return pa - pb, pa - pb - spread, pa - pb + spread


def compare(messaged_orders: int, messaged: int, holdout_orders: int, holdout: int, messaged_revenue: float = 0.0, holdout_revenue: float = 0.0) -> Comparison:
    """The comparison, or "not enough data" when either group is under the minimum."""
    smallest = min(messaged, holdout)
    if smallest < MIN_MESSAGING_GROUP:
        return Comparison(False, messaged, holdout, MIN_MESSAGING_GROUP - smallest)
    diff, low, high = two_proportion_interval(messaged_orders, messaged, holdout_orders, holdout)
    return Comparison(
        True, messaged, holdout, 0, messaged_orders / messaged, holdout_orders / holdout, diff, low, high, low <= 0 <= high,
        messaged_revenue / messaged, holdout_revenue / holdout,
    )


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _message_groups(db: Session, column, names: dict[int, str], since: datetime, include_dry_run: bool) -> dict[int | None, GroupStats]:
    base = [Message.queued_at >= since, column.is_not(None)]
    if not include_dry_run:
        base.append(Message.dry_run.is_(False))
    groups: dict[int | None, GroupStats] = {}
    rows = db.execute(
        select(
            column, Message.channel, Message.category,
            func.count().filter(Message.sent_at.is_not(None)), func.count().filter(Message.delivered_at.is_not(None)),
            func.count().filter(Message.read_at.is_not(None)), func.count().filter(Message.replied_at.is_not(None)),
            func.count().filter(Message.status == "failed"), func.count().filter(Message.status == "skipped"),
        ).where(*base).group_by(column, Message.channel, Message.category)
    )
    for key, channel, category, sent, delivered, read, replied, failed, skipped in rows:
        g = groups.setdefault(key, GroupStats(key, names.get(key, f"#{key}"), {}))
        g.sent += sent
        g.delivered += max(delivered, read)
        g.read += read
        g.replied += replied
        g.failed += failed
        g.skipped += skipped
        g.channel_mix[channel] = g.channel_mix.get(channel, 0) + sent
        if channel == "whatsapp":
            if category == "utility":
                g.whatsapp_utility += sent
            else:
                g.whatsapp_marketing += sent
    _add_outcomes(db, column, groups, since, include_dry_run)
    return groups


def _add_outcomes(db: Session, column, groups: dict, since: datetime, include_dry_run: bool) -> None:
    """Orders and revenue within 7 days after a message, and opt-outs within 7 days, per group."""
    day = func.date(Message.sent_at)
    query = (
        select(column, Order.id, Order.order_value)
        .join(Order, (Order.customer_id == Message.customer_id) & (Order.order_date >= day) & (Order.order_date <= day + WINDOW_DAYS))
        .where(Message.queued_at >= since, column.is_not(None), Message.sent_at.is_not(None)).distinct()
    )
    if not include_dry_run:
        query = query.where(Message.dry_run.is_(False))
    for key, _, value in db.execute(query):
        if key in groups:
            groups[key].orders += 1
            groups[key].revenue += float(value)
    blame = (
        select(ConsentEvent.id, column)
        .join(Message, (Message.customer_id == ConsentEvent.customer_id) & (Message.channel == ConsentEvent.channel)
              & (Message.sent_at.is_not(None)) & (Message.sent_at <= ConsentEvent.at) & (Message.sent_at >= ConsentEvent.at - timedelta(days=WINDOW_DAYS)))
        .where(ConsentEvent.action == "opt_out", ConsentEvent.at >= since)
        .order_by(ConsentEvent.id, Message.sent_at.desc()).ext(distinct_on(ConsentEvent.id))
    )
    if not include_dry_run:
        blame = blame.where(Message.dry_run.is_(False))
    for _, key in db.execute(blame):
        if key in groups:
            groups[key].opt_outs += 1


def journey_comparison(db: Session, journey: Journey, now: datetime, include_dry_run: bool) -> Comparison:
    """Messaged vs holdout for one journey (see the module note)."""
    if not include_dry_run and not db.scalar(select(func.count()).select_from(Message).where(Message.journey_id == journey.id, Message.dry_run.is_(False), Message.sent_at.is_not(None))):
        return Comparison(False, 0, 0, MIN_MESSAGING_GROUP, reason="no_real_messages")
    mature = now - timedelta(days=WINDOW_DAYS)
    rows = list(db.scalars(select(JourneyEnrollment).where(JourneyEnrollment.journey_id == journey.id, JourneyEnrollment.anchor_at <= mature)))
    if not rows:
        return Comparison(False, 0, 0, MIN_MESSAGING_GROUP, reason="too_new")
    results = {True: [0, 0, 0.0], False: [0, 0, 0.0]}            # holdout? -> [customers, customers with an order, revenue]
    for enrollment in rows:
        start: date = enrollment.anchor_at.date()
        orders = db.execute(select(Order.order_value).where(
            Order.customer_id == enrollment.customer_id, Order.order_date >= start, Order.order_date <= start + timedelta(days=WINDOW_DAYS))).scalars().all()
        bucket = results[bool(enrollment.holdout)]
        bucket[0] += 1
        bucket[1] += int(bool(orders))
        bucket[2] += float(sum(orders))
    messaged, holdout = results[False], results[True]
    return compare(messaged[1], messaged[0], holdout[1], holdout[0], messaged[2], holdout[2])


def build(db: Session, days: int = 90, include_dry_run: bool = False) -> dict:
    since = _since(days)
    now = datetime.now(timezone.utc)
    template_names = {t.id: t.name for t in db.scalars(select(MessageTemplate))}
    campaign_names = {c.id: c.name for c in db.scalars(select(Campaign))}
    journeys = list(db.scalars(select(Journey).order_by(Journey.id)))
    journey_names = {j.id: j.name for j in journeys}
    templates = _message_groups(db, Message.template_id, template_names, since, include_dry_run)
    campaigns_ = _message_groups(db, Message.campaign_id, campaign_names, since, include_dry_run)
    journeys_ = _message_groups(db, Message.journey_id, journey_names, since, include_dry_run)
    row = get_row(db)
    utility = sum(g.whatsapp_utility for g in templates.values())
    marketing = sum(g.whatsapp_marketing for g in templates.values())
    return {
        "days": days, "include_dry_run": include_dry_run, "templates": sorted(templates.values(), key=lambda g: -g.sent),
        "campaigns": sorted(campaigns_.values(), key=lambda g: -g.sent), "journeys": journeys_,
        "journey_rows": [(j, journeys_.get(j.id), journey_comparison(db, j, now, include_dry_run)) for j in journeys],
        "totals": {
            "sent": sum(g.sent for g in templates.values()), "delivered": sum(g.delivered for g in templates.values()), "read": sum(g.read for g in templates.values()),
            "replied": sum(g.replied for g in templates.values()), "failed": sum(g.failed for g in templates.values()), "skipped": sum(g.skipped for g in templates.values()),
            "opt_outs": sum(g.opt_outs for g in templates.values()), "orders": sum(g.orders for g in templates.values()), "revenue": sum(g.revenue for g in templates.values()),
        },
        "cost": {
            "utility_messages": utility, "marketing_messages": marketing,
            "utility_rate": float(row.cost_utility) if row.cost_utility is not None else None,
            "marketing_rate": float(row.cost_marketing) if row.cost_marketing is not None else None,
        },
    }
