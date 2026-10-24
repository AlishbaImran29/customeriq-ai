"""Journeys: automatic follow-ups by customer segment (Auto Messenger part 5).

HOW IT WORKS
- Every day the segments are worked out again (the same RFM segmentation as the dashboard). A customer who is in a
  journey's segment, and has agreed to be messaged, is ENROLLED. A customer who left the segment is taken off.
- A random 10% of each journey's customers (the "holdout", fixed by a hash so it never changes) are enrolled but NEVER
  messaged. They are the control group that lets Part 6 show what the messages really did.
- Each hour the due steps run. A step sends the template of its event on the channel the customer agreed to
  (WhatsApp first, else email), through the same door as every other message (consent, weekly cap, quiet hours,
  never twice).
- A journey STOPS for a customer when they order again, reply to us, opt out, or leave the segment.
- Step days count from the anchor: the day the customer joined ("enrollment") or the day of their first order
  ("first_order"). After the last step a journey may loop (every N days) up to `max_sends` messages in total, and never
  more than `max_per_30_days` in any 30 days.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Customer, CustomerConsent, IncomingMessage, Journey, JourneyEnrollment, Message, Order, SchedulerState
from app.services.messaging import campaigns, journey_defaults, policy, service
from app.services.messaging.settings_store import get_row
from app.services.order_status import customer_language, pick_template

logger = logging.getLogger(__name__)

MAX_ENROL_PER_RUN = 1000
MAX_STEPS_PER_RUN = 100
DAILY_KEY = "journeys_daily"
RETRY_AFTER = timedelta(days=1)


def is_holdout(journey_id: int, customer_id: int, percent: int) -> bool:
    """A stable pseudo-random choice: the same customer on the same journey always gets the same answer, and about
    `percent` out of every 100 customers are chosen."""
    if percent <= 0:
        return False
    digest = hashlib.sha256(f"holdout:{journey_id}:{customer_id}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % 10_000 < percent * 100


def seed_journeys(db: Session) -> int:
    """Add the default journeys that are missing (disabled). Returns how many were added. Does not commit."""
    added = 0
    for spec in journey_defaults.JOURNEYS:
        if db.scalar(select(Journey.id).where(Journey.key == spec["key"])) is None:
            db.add(Journey(enabled=False, **spec))
            added += 1
    db.flush()
    return added


def trigger_key(journey: Journey) -> str:
    return campaigns.SEGMENT_KEYS.get(journey.trigger_segment, campaigns.OTHER)


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def first_order_date(db: Session, customer_id: int) -> date | None:
    return db.scalar(select(func.min(Order.order_date)).where(Order.customer_id == customer_id))


def first_due(journey: Journey, customer_id: int, db: Session, now: datetime) -> datetime | None:
    """When the first step is due for a customer starting now; None when the journey is no use to them (every step is long past)."""
    first_day = journey.steps[0]["day"]
    if journey.anchor == "first_order":
        first = first_order_date(db, customer_id)
        if first is None:
            return None
        base = _midnight(first)
        last = base + timedelta(days=journey.steps[-1]["day"])
        if last + timedelta(days=journey.grace_days) < now:
            return None                                        # their first order is too long ago for this journey
        return base + timedelta(days=first_day)
    return now + timedelta(days=first_day)


def _reachable(consent: dict[tuple[int, str], bool], customer: Customer) -> bool:
    return campaigns.pick_channel(consent, customer) is not None


def _consent_for(db: Session, customer_ids: list[int]) -> dict[tuple[int, str], bool]:
    out: dict[tuple[int, str], bool] = {}
    for start in range(0, len(customer_ids), 1000):
        for row in db.scalars(select(CustomerConsent).where(CustomerConsent.customer_id.in_(customer_ids[start:start + 1000]))):
            out[(row.customer_id, row.channel)] = row.opted_in
    return out


@dataclass
class DailyResult:
    enrolled: int = 0
    holdout: int = 0
    left_segment: int = 0


def daily_refresh(db: Session, now: datetime) -> DailyResult:
    """Re-run the segmentation, take customers off journeys whose segment they left, and enrol new ones."""
    result = DailyResult()
    row = get_row(db)
    segment_of = campaigns.segment_by_customer(db)
    for journey in db.scalars(select(Journey).where(Journey.enabled.is_(True)).order_by(Journey.id)):
        key = trigger_key(journey)
        # 1. customers who are no longer in the segment
        for enrollment in db.scalars(select(JourneyEnrollment).where(JourneyEnrollment.journey_id == journey.id, JourneyEnrollment.state.in_(("active", "holdout")))):
            if segment_of.get(enrollment.customer_id) != key:
                _end(enrollment, "stopped", "segment_changed", now)
                result.left_segment += 1
        # 2. customers who are in the segment now
        wanted = sorted(cid for cid, seg in segment_of.items() if seg == key)
        if not wanted:
            continue
        on_it = set(db.scalars(select(JourneyEnrollment.customer_id).where(JourneyEnrollment.journey_id == journey.id, JourneyEnrollment.state.in_(("active", "holdout")))))
        candidates = [cid for cid in wanted if cid not in on_it]
        consent = _consent_for(db, candidates)
        for cid in candidates:
            if result.enrolled + result.holdout >= MAX_ENROL_PER_RUN:
                break
            customer = db.get(Customer, cid)
            if customer is None or not _reachable(consent, customer) or not _may_join_again(db, journey, cid):
                continue
            due = first_due(journey, cid, db, now)
            if due is None:
                continue
            held = is_holdout(journey.id, cid, row.holdout_percent)
            db.add(JourneyEnrollment(
                journey_id=journey.id, customer_id=cid, enrolled_at=now, anchor_at=due, holdout=held,
                state="holdout" if held else "active", next_run_at=None if held else due,
            ))
            result.holdout += int(held)
            result.enrolled += int(not held)
    db.flush()
    return result


def _may_join_again(db: Session, journey: Journey, customer_id: int) -> bool:
    """A customer who finished a journey may join it again only if they came back (ordered) since they joined it."""
    previous = db.scalar(select(JourneyEnrollment).where(JourneyEnrollment.journey_id == journey.id, JourneyEnrollment.customer_id == customer_id).order_by(JourneyEnrollment.id.desc()).limit(1))
    if previous is None:
        return True
    return db.scalar(select(func.count()).select_from(Order).where(Order.customer_id == customer_id, Order.order_date > previous.enrolled_at.date())) not in (None, 0)


def _end(enrollment: JourneyEnrollment, state: str, reason: str | None, now: datetime) -> None:
    enrollment.state, enrollment.stop_reason, enrollment.next_run_at, enrollment.ended_at = state, reason, None, now


def stop_reason(db: Session, enrollment: JourneyEnrollment) -> str | None:
    """Why this customer should no longer be messaged on this journey, or None to carry on."""
    since = enrollment.enrolled_at
    if db.scalar(select(func.count()).select_from(Order).where(Order.customer_id == enrollment.customer_id, Order.order_date > since.date())):
        return "ordered_again"
    if db.scalar(select(func.count()).select_from(IncomingMessage).where(IncomingMessage.customer_id == enrollment.customer_id, IncomingMessage.received_at > since)):
        return "replied"
    customer = db.get(Customer, enrollment.customer_id)
    if customer is None or not _reachable(_consent_for(db, [enrollment.customer_id]), customer):
        return "opted_out"
    return None


def sent_last_30_days(db: Session, journey_id: int, customer_id: int, now: datetime) -> int:
    return int(db.scalar(select(func.count()).select_from(Message).where(
        Message.journey_id == journey_id, Message.customer_id == customer_id, Message.status.in_(("queued", "sent", "delivered", "read", "replied")),
        Message.queued_at > now - timedelta(days=30),
    )) or 0)


def process_due(db: Session, settings: Settings, now: datetime, limit: int = MAX_STEPS_PER_RUN) -> dict[str, int]:
    counts = {"sent": 0, "stopped": 0, "completed": 0, "waiting": 0, "skipped": 0}
    row = get_row(db)
    due = db.scalars(
        select(JourneyEnrollment).join(Journey, Journey.id == JourneyEnrollment.journey_id)
        .where(JourneyEnrollment.state == "active", JourneyEnrollment.next_run_at <= now, Journey.enabled.is_(True))
        .order_by(JourneyEnrollment.next_run_at, JourneyEnrollment.id).limit(limit)
    ).all()
    for enrollment in due:
        journey = db.get(Journey, enrollment.journey_id)
        reason = stop_reason(db, enrollment)
        if reason is not None:
            _end(enrollment, "stopped", reason, now)
            counts["stopped"] += 1
            continue
        _run_step(db, settings, journey, enrollment, row, now, counts)
    return counts


def _run_step(db: Session, settings: Settings, journey: Journey, enrollment: JourneyEnrollment, row, now: datetime, counts: dict[str, int]) -> None:
    steps = journey.steps
    index = enrollment.step_index
    step = steps[index]
    # A step that is too late (for example a "day 7" message when the customer joined on day 30) is skipped, not sent.
    if journey.anchor == "first_order" and enrollment.next_run_at and now > enrollment.next_run_at + timedelta(days=journey.grace_days):
        counts["skipped"] += 1
        _advance(journey, enrollment, now, sent=False)
        return
    if journey.max_per_30_days and sent_last_30_days(db, journey.id, enrollment.customer_id, now) >= journey.max_per_30_days:
        enrollment.next_run_at = now + RETRY_AFTER
        counts["waiting"] += 1
        return
    customer = db.get(Customer, enrollment.customer_id)
    consent = _consent_for(db, [enrollment.customer_id])
    channel = campaigns.pick_channel(consent, customer) if customer else None
    if channel is None:
        _end(enrollment, "stopped", "opted_out", now)
        counts["stopped"] += 1
        return
    language = customer_language(customer, row.default_language)
    template = pick_template(db, step["event"], channel, language, row.default_language)
    if template is None or not template.approved_by_seller:
        enrollment.next_run_at = now + RETRY_AFTER          # wait: the seller has not approved the wording yet (no record is made)
        counts["waiting"] += 1
        return
    values = campaigns.campaign_variables(db, customer, None, _NoCampaign(journey.name), row, template.language, trigger_key(journey))
    # The date is part of the key so that a step held back by the weekly cap can be tried again on a later day, while a
    # second pass on the SAME day still sends nothing new.
    message = service.send_message(
        db, settings, customer, channel, template, values, event_key=f"journey:{journey.id}:{enrollment.id}:{enrollment.sends + 1}:{now.date().isoformat()}",
        journey_id=journey.id, now=now,
    )
    if message.status == "skipped" and message.error == "weekly_cap":
        enrollment.next_run_at = now + RETRY_AFTER          # the weekly cap is full: try again tomorrow
        counts["waiting"] += 1
        return
    sent = message.status != "skipped"
    counts["sent"] += int(sent)
    _advance(journey, enrollment, now, sent=sent)
    if enrollment.state == "completed":
        counts["completed"] += 1


class _NoCampaign:
    """Journey messages have no campaign: this gives campaign_variables the two things it reads (a name and no offer)."""

    def __init__(self, name: str) -> None:
        self.name, self.offer_text = name, None


def _advance(journey: Journey, enrollment: JourneyEnrollment, now: datetime, *, sent: bool) -> None:
    """Move to the next step, loop, or finish."""
    if sent:
        enrollment.sends += 1
        enrollment.last_sent_at = now
    steps = journey.steps
    nxt = enrollment.step_index + 1
    base = enrollment.anchor_at - timedelta(days=steps[0]["day"])
    if nxt < len(steps):
        enrollment.step_index = nxt
        enrollment.next_run_at = max(base + timedelta(days=steps[nxt]["day"]), now)
        return
    if journey.loop_every_days and (journey.max_sends is None or enrollment.sends < journey.max_sends):
        enrollment.step_index = 0
        enrollment.anchor_at = now + timedelta(days=journey.loop_every_days)
        enrollment.next_run_at = enrollment.anchor_at
        return
    _end(enrollment, "completed", None, now)


def _today_key(now: datetime, tz_name: str) -> str:
    return now.astimezone(policy.zone(tz_name)).date().isoformat()


def run_journeys(db: Session, settings: Settings, now: datetime | None = None) -> dict[str, int]:
    """The scheduler's journey pass: the daily refresh (once a day), then every due step."""
    now = now or datetime.now(timezone.utc)
    row = get_row(db)
    counts: dict[str, int] = {"enrolled": 0, "holdout": 0, "left_segment": 0}
    today = _today_key(now, row.timezone)
    state = db.get(SchedulerState, DAILY_KEY)
    if state is None or state.value != today:
        daily = daily_refresh(db, now)
        counts.update(enrolled=daily.enrolled, holdout=daily.holdout, left_segment=daily.left_segment)
        if state is None:
            db.add(SchedulerState(key=DAILY_KEY, value=today))
        else:
            state.value = today
        db.flush()
    counts.update(process_due(db, settings, now))
    return counts
