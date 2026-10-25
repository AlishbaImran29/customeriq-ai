"""Auto Messenger part 5: journeys, the holdout group, stop conditions and the scheduler. Everything is made up (TEST)."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.config import Settings, get_settings
from app.main import app
from app.models import Customer, IncomingMessage, Journey, JourneyEnrollment, Message, MessageTemplate, Order, SchedulerState
from app.services.messaging import campaigns, consent, journey_defaults, journeys, scheduler
from app.services.messaging.defaults import seed_defaults
from app.services.messaging.render import check_template_text
from app.services.messaging.settings_store import get_row

NOW = datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc)                  # 12:00 in Pakistan: not in quiet hours
_n = [0]


def settings(**changes) -> Settings:
    return Settings(_env_file=None, messaging_dry_run=True, **changes)


def customer(db, *, name="Test Ali", wa=True, mail=False, first_order=date(2026, 1, 1)):
    _n[0] += 1
    phone = f"+92300{_n[0]:07d}"
    c = Customer(external_id=f"TEST-J{_n[0]}", first_name=name, phone=phone, phone_normalised=phone, email=f"j{_n[0]}.test@testcustomer.test", country="Pakistan")
    db.add(c)
    db.flush()
    db.add(Order(external_id=f"TEST-JO-{_n[0]}", customer_id=c.id, order_date=first_order, order_value=Decimal(1500), product_category="Shoes", products="Test shoes", source="manual"))
    if wa:
        consent.set_consent(db, c.id, "whatsapp", True, "manual")
    if mail:
        consent.set_consent(db, c.id, "email", True, "manual")
    db.flush()
    return c


def journey(db, key="at_risk", enabled=True, holdout_percent=0):
    journeys.seed_journeys(db)
    j = db.query(Journey).filter_by(key=key).one()
    j.enabled = enabled
    get_row(db).holdout_percent = holdout_percent
    db.flush()
    return j


def approve_templates(db, event_prefix="journey_"):
    seed_defaults(db, [], journey_defaults.journey_templates())
    for t in db.query(MessageTemplate).filter(MessageTemplate.event.like(event_prefix + "%")):
        t.approved_by_seller = True
    db.flush()


def segments(monkeypatch, mapping):
    monkeypatch.setattr(campaigns, "segment_by_customer", lambda db: dict(mapping))


# --- the defaults --------------------------------------------------------------------------------------------------------------


def test_the_default_journeys_match_the_brief_and_start_switched_off(db_session):
    assert journeys.seed_journeys(db_session) == 5 and journeys.seed_journeys(db_session) == 0
    by_key = {j.key: j for j in db_session.query(Journey)}
    assert all(not j.enabled for j in by_key.values())
    assert [s["day"] for s in by_key["at_risk"].steps] == [0, 7, 14] and by_key["at_risk"].loop_every_days is None
    assert (by_key["champions"].max_per_30_days, by_key["champions"].loop_every_days) == (2, 15)
    assert (by_key["loyal"].loop_every_days, by_key["loyal"].trigger_segment) == (14, "Loyal Customers")
    assert (by_key["potential"].anchor, [s["day"] for s in by_key["potential"].steps]) == ("first_order", [7, 21])
    assert (by_key["lost"].loop_every_days, by_key["lost"].max_sends) == (30, 2)


def test_every_default_journey_template_is_valid_and_whatsapp_ones_say_how_to_stop():
    rows = journey_defaults.journey_templates()
    events = {s["event"] for spec in journey_defaults.JOURNEYS for s in spec["steps"]}
    assert {r["event"] for r in rows} == events and len(rows) == len(events) * 4
    for r in rows:
        check_template_text(r["body"], r["subject"])
        assert r["category"] == "marketing"
        if r["channel"] == "whatsapp":
            assert "STOP" in r["body"]
        assert "%" not in r["body"] and "discount" not in r["body"].lower()               # no offer is invented


# --- the holdout --------------------------------------------------------------------------------------------------------------------


def test_the_holdout_is_stable_and_about_ten_percent():
    first = [journeys.is_holdout(1, c, 10) for c in range(5000)]
    assert first == [journeys.is_holdout(1, c, 10) for c in range(5000)]                       # the same answer every time
    assert 420 <= sum(first) <= 580                                                             # about 10% of 5,000
    assert first != [journeys.is_holdout(2, c, 10) for c in range(5000)]                       # a different journey picks different people
    assert not any(journeys.is_holdout(1, c, 0) for c in range(500)) and all(journeys.is_holdout(1, c, 100) for c in range(500))
    assert 1300 <= sum(journeys.is_holdout(1, c, 30) for c in range(5000)) <= 1700


# --- enrolling -------------------------------------------------------------------------------------------------------------------------


def test_only_reachable_customers_in_the_segment_are_enrolled(db_session, monkeypatch):
    j = journey(db_session)
    in_segment, silent, other = customer(db_session, name="Test Reachable"), customer(db_session, name="Test Silent", wa=False), customer(db_session, name="Test Other")
    segments(monkeypatch, {in_segment.id: "at_risk", silent.id: "at_risk", other.id: "loyal"})
    result = journeys.daily_refresh(db_session, NOW)
    assert (result.enrolled, result.holdout) == (1, 0)
    enrollment = db_session.query(JourneyEnrollment).one()
    assert (enrollment.customer_id, enrollment.state, enrollment.next_run_at, enrollment.journey_id) == (in_segment.id, "active", NOW, j.id)
    assert journeys.daily_refresh(db_session, NOW).enrolled == 0 and db_session.query(JourneyEnrollment).count() == 1            # no second enrolment


def test_a_disabled_journey_enrols_nobody(db_session, monkeypatch):
    journey(db_session, enabled=False)
    c = customer(db_session)
    segments(monkeypatch, {c.id: "at_risk"})
    assert journeys.daily_refresh(db_session, NOW).enrolled == 0


def test_holdout_customers_are_enrolled_but_never_messaged(db_session, monkeypatch):
    j = journey(db_session, holdout_percent=100)
    approve_templates(db_session)
    c = customer(db_session)
    segments(monkeypatch, {c.id: "at_risk"})
    result = journeys.daily_refresh(db_session, NOW)
    enrollment = db_session.query(JourneyEnrollment).one()
    assert (result.holdout, result.enrolled) == (1, 0) and enrollment.holdout and enrollment.state == "holdout" and enrollment.next_run_at is None
    assert enrollment.anchor_at == NOW                                                           # the day the first message WOULD have been due
    assert journeys.process_due(db_session, settings(), NOW + timedelta(days=30))["sent"] == 0 and db_session.query(Message).count() == 0 and j.id


def test_a_customer_who_left_the_segment_is_taken_off(db_session, monkeypatch):
    journey(db_session)
    c = customer(db_session)
    segments(monkeypatch, {c.id: "at_risk"})
    journeys.daily_refresh(db_session, NOW)
    segments(monkeypatch, {c.id: "loyal"})
    assert journeys.daily_refresh(db_session, NOW + timedelta(days=1)).left_segment == 1
    enrollment = db_session.query(JourneyEnrollment).one()
    assert (enrollment.state, enrollment.stop_reason, enrollment.next_run_at) == ("stopped", "segment_changed", None)


def test_a_finished_customer_may_join_again_only_after_ordering_again(db_session, monkeypatch):
    journey(db_session)
    c = customer(db_session)
    segments(monkeypatch, {c.id: "at_risk"})
    journeys.daily_refresh(db_session, NOW)
    enrollment = db_session.query(JourneyEnrollment).one()
    enrollment.state, enrollment.stop_reason = "stopped", "segment_changed"
    db_session.flush()
    assert journeys.daily_refresh(db_session, NOW + timedelta(days=5)).enrolled == 0                                   # still no new order
    db_session.add(Order(external_id="TEST-J-BACK", customer_id=c.id, order_date=(NOW + timedelta(days=3)).date(), order_value=Decimal(900), source="manual"))
    db_session.flush()
    assert journeys.daily_refresh(db_session, NOW + timedelta(days=6)).enrolled == 1


def test_a_first_order_journey_does_not_enrol_customers_whose_first_order_is_too_old(db_session, monkeypatch):
    journey(db_session, key="potential")
    fresh = customer(db_session, name="Test Fresh", first_order=(NOW - timedelta(days=5)).date())
    old = customer(db_session, name="Test Old", first_order=(NOW - timedelta(days=90)).date())
    segments(monkeypatch, {fresh.id: "potential", old.id: "potential"})
    assert journeys.daily_refresh(db_session, NOW).enrolled == 1
    enrollment = db_session.query(JourneyEnrollment).one()
    assert enrollment.customer_id == fresh.id
    assert enrollment.next_run_at == datetime.combine((NOW - timedelta(days=5)).date() + timedelta(days=7), datetime.min.time(), tzinfo=timezone.utc)      # day 7 after the first order


# --- running the steps -------------------------------------------------------------------------------------------------------------------


def test_the_at_risk_journey_sends_on_day_0_7_and_14_and_then_stops(db_session, monkeypatch):
    j = journey(db_session)
    approve_templates(db_session)
    c = customer(db_session, name="Test Ali")
    segments(monkeypatch, {c.id: "at_risk"})
    journeys.daily_refresh(db_session, NOW)
    enrollment = db_session.query(JourneyEnrollment).one()
    assert journeys.process_due(db_session, settings(), NOW)["sent"] == 1
    first = db_session.query(Message).one()
    assert first.journey_id == j.id and first.category == "marketing" and first.status == "sent" and first.rendered_text.startswith("Hello Test Ali, we have missed you")
    assert "Last time you bought Test shoes." in first.rendered_text and "Reply STOP" in first.rendered_text
    assert (enrollment.step_index, enrollment.sends, enrollment.next_run_at) == (1, 1, NOW + timedelta(days=7))
    assert journeys.process_due(db_session, settings(), NOW + timedelta(days=6))["sent"] == 0                         # not due yet
    assert journeys.process_due(db_session, settings(), NOW + timedelta(days=7))["sent"] == 1
    assert enrollment.next_run_at == NOW + timedelta(days=14)
    counts = journeys.process_due(db_session, settings(), NOW + timedelta(days=14))
    assert counts["sent"] == 1 and counts["completed"] == 1 and enrollment.state == "completed" and enrollment.sends == 3
    assert journeys.process_due(db_session, settings(), NOW + timedelta(days=60))["sent"] == 0 and db_session.query(Message).count() == 3


def test_a_late_run_still_sends_the_step_and_keeps_the_gap_to_the_next(db_session, monkeypatch):
    journey(db_session)
    approve_templates(db_session)
    c = customer(db_session)
    segments(monkeypatch, {c.id: "at_risk"})
    journeys.daily_refresh(db_session, NOW)
    journeys.process_due(db_session, settings(), NOW)
    journeys.process_due(db_session, settings(), NOW + timedelta(days=9))                                              # the scheduler was away for 2 days
    enrollment = db_session.query(JourneyEnrollment).one()
    assert enrollment.step_index == 2 and enrollment.next_run_at == NOW + timedelta(days=14)


def test_champions_get_at_most_two_messages_in_any_thirty_days(db_session, monkeypatch):
    j = journey(db_session, key="champions")
    approve_templates(db_session)
    c = customer(db_session)
    segments(monkeypatch, {c.id: "champions"})
    journeys.daily_refresh(db_session, NOW)
    sent_days = []
    for day in range(0, 61):
        if journeys.process_due(db_session, settings(), NOW + timedelta(days=day))["sent"]:
            sent_days.append(day)
    assert sent_days[:3] == [0, 15, 30]
    for start in range(0, 61):
        assert sum(1 for d in sent_days if start <= d < start + 30) <= 2
    assert j.max_per_30_days == 2


def test_lost_customers_get_one_message_a_month_twice_then_it_stops(db_session, monkeypatch):
    journey(db_session, key="lost")
    approve_templates(db_session)
    c = customer(db_session)
    segments(monkeypatch, {c.id: "lost"})
    journeys.daily_refresh(db_session, NOW)
    sent = [d for d in range(0, 120) if journeys.process_due(db_session, settings(), NOW + timedelta(days=d))["sent"]]
    assert sent == [0, 30]
    enrollment = db_session.query(JourneyEnrollment).one()
    assert enrollment.state == "completed" and enrollment.sends == 2


def test_loyal_customers_are_messaged_every_fourteen_days(db_session, monkeypatch):
    journey(db_session, key="loyal")
    approve_templates(db_session)
    c = customer(db_session)
    segments(monkeypatch, {c.id: "loyal"})
    journeys.daily_refresh(db_session, NOW)
    sent = [d for d in range(0, 50) if journeys.process_due(db_session, settings(), NOW + timedelta(days=d))["sent"]]
    assert sent == [0, 14, 28, 42]


def test_a_potential_loyalist_gets_day_7_and_day_21_after_the_first_order_and_a_missed_step_is_skipped(db_session, monkeypatch):
    journey(db_session, key="potential")
    approve_templates(db_session)
    ordered = (NOW - timedelta(days=5)).date()
    c = customer(db_session, first_order=ordered)
    segments(monkeypatch, {c.id: "potential"})
    journeys.daily_refresh(db_session, NOW)
    day7 = datetime.combine(ordered + timedelta(days=7), datetime.min.time(), tzinfo=timezone.utc)
    assert journeys.process_due(db_session, settings(), day7 - timedelta(hours=1))["sent"] == 0
    assert journeys.process_due(db_session, settings(), day7 + timedelta(hours=8))["sent"] == 1
    events = [m.template_id for m in db_session.query(Message)]
    assert len(events) == 1
    # the scheduler is down for 10 days: day 21 is more than the 3 days of grace late, so it is skipped, never sent
    counts = journeys.process_due(db_session, settings(), day7 + timedelta(days=18))
    assert counts["sent"] == 0 and counts["skipped"] == 1
    assert db_session.query(JourneyEnrollment).one().state == "completed" and db_session.query(Message).count() == 1


# --- stopping ------------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("what", ["order", "reply", "opt_out"])
def test_a_journey_stops_when_the_customer_orders_replies_or_opts_out(db_session, monkeypatch, what):
    journey(db_session)
    approve_templates(db_session)
    c = customer(db_session)
    segments(monkeypatch, {c.id: "at_risk"})
    journeys.daily_refresh(db_session, NOW)
    journeys.process_due(db_session, settings(), NOW)
    if what == "order":
        db_session.add(Order(external_id="TEST-J-NEW", customer_id=c.id, order_date=(NOW + timedelta(days=2)).date(), order_value=Decimal(800), source="manual"))
    elif what == "reply":
        db_session.add(IncomingMessage(customer_id=c.id, from_address=c.phone_normalised, provider_message_id="wamid.TEST-J-REPLY", message_type="text", body="thanks", received_at=NOW + timedelta(days=2)))
    else:
        consent.set_consent(db_session, c.id, "whatsapp", False, "whatsapp_stop")
    db_session.flush()
    counts = journeys.process_due(db_session, settings(), NOW + timedelta(days=7))
    enrollment = db_session.query(JourneyEnrollment).one()
    assert counts["sent"] == 0 and counts["stopped"] == 1
    assert (enrollment.state, enrollment.stop_reason) == ("stopped", {"order": "ordered_again", "reply": "replied", "opt_out": "opted_out"}[what])
    assert db_session.query(Message).count() == 1                                                    # only the first message was ever sent


def test_an_order_on_the_day_of_enrolment_does_not_count_as_ordering_again(db_session, monkeypatch):
    journey(db_session)
    approve_templates(db_session)
    c = customer(db_session)
    segments(monkeypatch, {c.id: "at_risk"})
    journeys.daily_refresh(db_session, NOW)
    db_session.add(Order(external_id="TEST-J-SAMEDAY", customer_id=c.id, order_date=NOW.date(), order_value=Decimal(800), source="manual"))
    db_session.flush()
    assert journeys.process_due(db_session, settings(), NOW)["sent"] == 1


def test_a_customer_with_only_an_email_agreement_is_messaged_by_email(db_session, monkeypatch):
    journey(db_session)
    approve_templates(db_session)
    c = customer(db_session, wa=False, mail=True)
    segments(monkeypatch, {c.id: "at_risk"})
    journeys.daily_refresh(db_session, NOW)
    journeys.process_due(db_session, settings(), NOW)
    message = db_session.query(Message).one()
    assert message.channel == "email" and message.subject.startswith("We have missed you")


def test_unapproved_wording_waits_without_creating_a_record_and_goes_out_once_approved(db_session, monkeypatch):
    journey(db_session)
    seed_defaults(db_session, [], journey_defaults.journey_templates())                              # added, but NOT approved
    c = customer(db_session)
    segments(monkeypatch, {c.id: "at_risk"})
    journeys.daily_refresh(db_session, NOW)
    counts = journeys.process_due(db_session, settings(), NOW)
    enrollment = db_session.query(JourneyEnrollment).one()
    assert counts["waiting"] == 1 and db_session.query(Message).count() == 0 and enrollment.step_index == 0 and enrollment.next_run_at == NOW + timedelta(days=1)
    for t in db_session.query(MessageTemplate):
        t.approved_by_seller = True
    db_session.flush()
    assert journeys.process_due(db_session, settings(), NOW + timedelta(days=1))["sent"] == 1


def test_a_full_weekly_cap_makes_the_step_wait_a_day(db_session, monkeypatch):
    journey(db_session)
    approve_templates(db_session)
    c = customer(db_session)
    get_row(db_session).weekly_marketing_cap = 1
    db_session.add(Message(customer_id=c.id, channel="whatsapp", category="marketing", rendered_text="earlier promo", status="sent", idempotency_key="test-j-earlier", queued_at=NOW - timedelta(days=1), sent_at=NOW - timedelta(days=1)))
    segments(monkeypatch, {c.id: "at_risk"})
    journeys.daily_refresh(db_session, NOW)
    counts = journeys.process_due(db_session, settings(), NOW)
    enrollment = db_session.query(JourneyEnrollment).one()
    assert counts["waiting"] == 1 and enrollment.step_index == 0 and enrollment.next_run_at == NOW + timedelta(days=1)
    assert journeys.process_due(db_session, settings(), NOW + timedelta(days=7))["sent"] == 1               # a week later the cap has room


def test_a_disabled_journey_does_not_run_even_for_people_already_on_it(db_session, monkeypatch):
    j = journey(db_session)
    approve_templates(db_session)
    c = customer(db_session)
    segments(monkeypatch, {c.id: "at_risk"})
    journeys.daily_refresh(db_session, NOW)
    j.enabled = False
    db_session.flush()
    assert journeys.process_due(db_session, settings(), NOW)["sent"] == 0 and db_session.query(Message).count() == 0


# --- the scheduler -----------------------------------------------------------------------------------------------------------------------------


def test_the_daily_refresh_runs_once_a_day_but_the_steps_run_every_pass(db_session, monkeypatch):
    journey(db_session)
    approve_templates(db_session)
    first = customer(db_session, name="Test First")
    segments(monkeypatch, {first.id: "at_risk"})
    assert journeys.run_journeys(db_session, settings(), NOW)["enrolled"] == 1 and db_session.get(SchedulerState, "journeys_daily").value == "2026-03-10"
    second = customer(db_session, name="Test Second")
    segments(monkeypatch, {first.id: "at_risk", second.id: "at_risk"})
    assert journeys.run_journeys(db_session, settings(), NOW + timedelta(hours=1))["enrolled"] == 0               # the same day: not refreshed again
    assert journeys.run_journeys(db_session, settings(), NOW + timedelta(days=1))["enrolled"] == 1                # the next day: refreshed


def test_the_day_changes_at_midnight_pakistan_time_not_utc(db_session, monkeypatch):
    journey(db_session)
    c = customer(db_session)
    segments(monkeypatch, {c.id: "at_risk"})
    journeys.run_journeys(db_session, settings(), datetime(2026, 3, 10, 18, 30, tzinfo=timezone.utc))               # 23:30 on the 10th in Pakistan
    assert db_session.get(SchedulerState, "journeys_daily").value == "2026-03-10"
    journeys.run_journeys(db_session, settings(), datetime(2026, 3, 10, 19, 30, tzinfo=timezone.utc))               # 00:30 on the 11th
    assert db_session.get(SchedulerState, "journeys_daily").value == "2026-03-11"


def test_run_due_runs_every_part_and_one_failing_part_does_not_stop_the_others(db_session, monkeypatch):
    results = scheduler.run_due(db_session, settings(), NOW)
    assert set(results) == {"queue", "media", "reviews", "cod", "workflows", "leads", "carts", "meta_events", "campaigns", "journeys"} and "error" not in {k for r in results.values() for k in r}

    def boom(*args, **kwargs):
        raise RuntimeError("the campaign code broke")

    monkeypatch.setattr(campaigns, "send_due_batches", boom)
    again = scheduler.run_due(db_session, settings(), NOW)
    assert again["campaigns"] == {"error": 1} and "error" not in again["journeys"] and "error" not in again["queue"]


def test_the_scheduler_endpoint_needs_the_secret(db_client):
    def call(**headers):
        return db_client.post("/api/v1/internal/run-scheduler", headers=headers)

    from app.api.deps import require_user

    app.dependency_overrides.pop(require_user, None)                                              # it must work without a sign-in
    app.dependency_overrides[get_settings] = lambda: settings()
    assert call(**{"X-Scheduler-Secret": "anything"}).status_code == 503                         # no secret configured: refuses everyone
    app.dependency_overrides[get_settings] = lambda: settings(scheduler_secret="test-scheduler-secret")
    assert call().status_code == 403
    assert call(**{"X-Scheduler-Secret": "wrong"}).status_code == 403
    assert call(**{"X-Scheduler-Secret": "test-scheduler-secret "}).status_code == 403
    ok = call(**{"X-Scheduler-Secret": "test-scheduler-secret"})
    assert ok.status_code == 200 and ok.json()["ok"] is True and set(ok.json()["results"]) == {"queue", "media", "reviews", "cod", "workflows", "leads", "carts", "meta_events", "campaigns", "journeys"}


# --- HTTP ----------------------------------------------------------------------------------------------------------------------------------------


def test_journeys_over_http(db_client, db_session, monkeypatch):
    app.dependency_overrides[get_settings] = lambda: settings()
    assert db_client.get("/api/v1/messaging/journeys").json() == []
    seeded = db_client.post("/api/v1/messaging/journeys/seed-defaults").json()
    assert seeded == {"journeys": 5, "templates": 32} and db_client.post("/api/v1/messaging/journeys/seed-defaults").json() == {"journeys": 0, "templates": 0}
    listed = db_client.get("/api/v1/messaging/journeys").json()
    risk = next(j for j in listed if j["key"] == "at_risk")
    assert risk["enabled"] is False and risk["templatesReady"] is False and risk["counts"] == {"active": 0, "holdout": 0, "completed": 0, "stopped": {}}

    changed = db_client.patch(f"/api/v1/messaging/journeys/{risk['id']}", json={"enabled": True, "name": "My win-back", "steps": [{"day": 0, "event": "journey_at_risk_1"}, {"day": 5, "event": "journey_at_risk_2"}], "maxSends": 3}).json()
    assert changed["enabled"] is True and changed["name"] == "My win-back" and [s["day"] for s in changed["steps"]] == [0, 5] and changed["maxSends"] == 3
    assert db_client.patch(f"/api/v1/messaging/journeys/{risk['id']}", json={"maxSends": None}).json()["maxSends"] is None                  # None clears it
    assert db_client.patch(f"/api/v1/messaging/journeys/{risk['id']}", json={"steps": [{"day": 7, "event": "journey_at_risk_1"}, {"day": 3, "event": "journey_at_risk_2"}]}).status_code == 422
    assert db_client.patch(f"/api/v1/messaging/journeys/{risk['id']}", json={"steps": [{"day": 1, "event": "Bad Event!"}]}).status_code == 422
    assert db_client.patch("/api/v1/messaging/journeys/999999", json={"enabled": True}).status_code == 404

    for t in db_session.query(MessageTemplate).filter(MessageTemplate.event.in_(["journey_at_risk_1", "journey_at_risk_2"])):
        t.approved_by_seller = True
    db_session.flush()
    assert next(j for j in db_client.get("/api/v1/messaging/journeys").json() if j["key"] == "at_risk")["templatesReady"] is True

    c = customer(db_session, name="Test Ali")
    segments(monkeypatch, {c.id: "at_risk"})
    get_row(db_session).holdout_percent = 0
    db_session.flush()
    ran = db_client.post("/api/v1/messaging/journeys/run-now").json()
    assert ran["enrolled"] == 1
    people = db_client.get(f"/api/v1/messaging/journeys/{risk['id']}/enrollments").json()
    assert people[0]["customerName"] == "Test Ali" and people[0]["state"] == "active" and people[0]["holdout"] is False
    assert db_client.get(f"/api/v1/messaging/journeys/{risk['id']}/enrollments?state=holdout").json() == []
    assert db_client.get(f"/api/v1/messaging/journeys/{risk['id']}/enrollments?state=bogus").status_code == 422


def test_seeding_templates_through_the_templates_endpoint_includes_journeys(db_client):
    assert db_client.post("/api/v1/messaging/templates/seed-defaults", json={"groups": ["journeys"]}).json()["added"] == 32
