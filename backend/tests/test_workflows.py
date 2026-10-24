"""The automation engine: allowlisted definitions, conditions (no eval), durable jobs, retries, loop protection, dry run.
Customers, orders and messages are made up (marked TEST); nothing is really sent."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.models import Customer, Job, Message, Task, Workflow, WorkflowRun
from app.services.workflows import actions as wf_actions
from app.services.workflows import conditions, engine, spec
from tests.test_order_status import make_customer, make_order, make_template, opt_in

NOON = datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc)


def settings(**kw) -> Settings:
    return Settings(_env_file=None, messaging_dry_run=True, **kw)


def rule(field, operator, value):
    return {"field": field, "operator": operator, "value": value}


def make_workflow(db, *, trigger="order_created", conditions_=None, steps=None, enabled=True, config=None, name="Test workflow"):
    w = Workflow(name=name, trigger=trigger, trigger_config=config or {}, conditions=conditions_ or {}, actions=steps or [{"type": "add_tag", "params": {"tag": "new"}}], enabled=enabled)
    db.add(w)
    db.flush()
    return w


# --- the allowlist ---------------------------------------------------------------------------------------------------------


def test_a_valid_definition_has_no_problems():
    assert spec.check("order_created", {}, {"op": "and", "rules": [rule("order_total", "gt", 5000)]}, [{"type": "add_tag", "params": {"tag": "big"}, "delayMinutes": 5}]) == []


@pytest.mark.parametrize("trigger,conds,steps,fragment", [
    ("nope", {}, [{"type": "add_tag", "params": {"tag": "x"}}], "Unknown trigger"),
    ("order_created", {"rules": [rule("__import__('os')", "eq", 1)]}, [{"type": "add_tag", "params": {"tag": "x"}}], "unknown field"),
    ("order_created", {"rules": [rule("order_total", "contains", "5")]}, [{"type": "add_tag", "params": {"tag": "x"}}], "cannot be used"),
    ("order_created", {"rules": [rule("order_total", "gt", "5000")]}, [{"type": "add_tag", "params": {"tag": "x"}}], "must be a number"),
    ("schedule_daily", {"rules": [rule("order_total", "gt", 1)]}, [{"type": "notify", "params": {"title": "x"}}], "not known for this trigger"),
    ("order_created", {}, [], "at least one action"),
    ("order_created", {}, [{"type": "rm_rf", "params": {}}], "unknown action"),
    ("schedule_daily", {}, [{"type": "send_message", "params": {"channel": "email", "event": "x"}}], "needs a customer"),
    ("order_created", {}, [{"type": "add_tag", "params": {"tag": "x"}, "delayMinutes": -1}], "wait must be"),
    ("order_created", {}, [{"type": "call_webhook", "params": {"url": "http://insecure.example"}}], "https://"),
    ("customer_inactive", {}, [{"type": "notify", "params": {"title": "x"}}], "days of silence"),
])
def test_bad_definitions_are_refused_with_a_plain_reason(trigger, conds, steps, fragment):
    config = {} if trigger != "customer_inactive" else {}
    assert any(fragment in p for p in spec.check(trigger, config, conds, steps))


# --- conditions: data, never code -------------------------------------------------------------------------------------------


def test_conditions_and_or_and_missing_facts():
    facts = {"order_total": 6000, "order_city": "Lahore", "customer_tags": ["VIP"], "customer_whatsapp_consent": True}
    both = {"op": "and", "rules": [rule("order_total", "gt", 5000), rule("order_city", "eq", "lahore")]}
    assert conditions.evaluate(both, facts)[0] is True
    assert conditions.evaluate({"op": "and", "rules": [rule("order_total", "gt", 9000), rule("order_city", "eq", "Lahore")]}, facts)[0] is False
    assert conditions.evaluate({"op": "or", "rules": [rule("order_total", "gt", 9000), rule("order_city", "in", ["Karachi", "Lahore"])]}, facts)[0] is True
    assert conditions.evaluate({"rules": [rule("customer_tags", "contains", "vip")]}, facts)[0] is True
    assert conditions.evaluate({"rules": [rule("customer_whatsapp_consent", "eq", True)]}, facts)[0] is True
    assert conditions.evaluate({"rules": [rule("stock_available", "lt", 3)]}, facts)[0] is False        # a fact that is not there never matches
    assert conditions.evaluate({}, facts) == (True, [])


def test_a_condition_value_is_never_evaluated():
    matched, _ = conditions.evaluate({"rules": [rule("order_city", "eq", "__import__('os').system('x')")]}, {"order_city": "Lahore"})
    assert matched is False


# --- events start runs; the same event never starts two ------------------------------------------------------------------------


def test_an_event_starts_a_run_only_for_enabled_matching_workflows(db_session):
    customer = make_customer(db_session)
    big = make_order(db_session, customer, value=9000)
    on = make_workflow(db_session, conditions_={"rules": [rule("order_total", "gt", 5000)]})
    make_workflow(db_session, conditions_={"rules": [rule("order_total", "gt", 50000)]}, name="too high")
    make_workflow(db_session, enabled=False, name="off")
    runs = engine.emit(db_session, settings(), "order_created", {"order_id": big.id, "customer_id": customer.id}, f"order_created:{big.id}", NOON)
    assert [r.workflow_id for r in runs] == [on.id]
    assert runs[0].context["facts"]["order_total"] == 9000.0                                  # what it saw is kept
    again = engine.emit(db_session, settings(), "order_created", {"order_id": big.id, "customer_id": customer.id}, f"order_created:{big.id}", NOON)
    assert again == [] and db_session.query(WorkflowRun).count() == 1                         # same event, no second run


def test_delays_queue_one_step_at_a_time(db_session):
    customer = make_customer(db_session)
    order = make_order(db_session, customer)
    w = make_workflow(db_session, steps=[{"type": "add_tag", "params": {"tag": "a"}, "delayMinutes": 0}, {"type": "add_tag", "params": {"tag": "b"}, "delayMinutes": 60}])
    engine.emit(db_session, settings(), "order_created", {"order_id": order.id, "customer_id": customer.id}, "k1", NOON)
    assert [(j.step_index, j.run_at) for j in db_session.query(Job)] == [(0, NOON)]            # only the first step is queued
    engine.run_due_jobs(db_session, settings(), NOON)
    steps = {j.step_index: j for j in db_session.query(Job)}
    assert steps[0].status == "done" and steps[1].status == "pending" and steps[1].run_at == NOON + timedelta(minutes=60)
    assert db_session.get(Customer, customer.id).tags == ["a"]
    engine.run_due_jobs(db_session, settings(), NOON + timedelta(minutes=30))
    assert db_session.get(Customer, customer.id).tags == ["a"]                                # not yet
    engine.run_due_jobs(db_session, settings(), NOON + timedelta(minutes=61))
    run = db_session.query(WorkflowRun).one()
    assert db_session.get(Customer, customer.id).tags == ["a", "b"] and run.status == "done" and w.id == run.workflow_id


# --- actions ---------------------------------------------------------------------------------------------------------------------


def test_send_message_goes_through_consent_and_is_logged(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    make_template(db_session, "order_confirmed")
    order = make_order(db_session, customer)
    make_workflow(db_session, steps=[{"type": "send_message", "params": {"channel": "whatsapp", "event": "order_confirmed"}}])
    engine.emit(db_session, settings(), "order_created", {"order_id": order.id, "customer_id": customer.id}, "k2", NOON)
    engine.run_due_jobs(db_session, settings(), NOON)
    message = db_session.query(Message).one()
    assert message.status in ("sent", "queued") and message.idempotency_key.endswith(":wf:" + str(db_session.query(WorkflowRun).one().id) + ":0")
    assert db_session.query(Job).one().result["message_id"] == message.id


def test_a_customer_who_did_not_agree_is_not_messaged_but_the_step_is_logged(db_session):
    customer = make_customer(db_session)
    make_template(db_session, "order_confirmed")
    order = make_order(db_session, customer)
    make_workflow(db_session, steps=[{"type": "send_message", "params": {"channel": "whatsapp", "event": "order_confirmed"}}])
    engine.emit(db_session, settings(), "order_created", {"order_id": order.id, "customer_id": customer.id}, "k3", NOON)
    engine.run_due_jobs(db_session, settings(), NOON)
    job = db_session.query(Job).one()
    assert job.status == "done" and job.result["status"] == "skipped" and job.result["reason"] == "no_consent"


def test_tasks_tags_and_status_changes(db_session):
    customer = make_customer(db_session, name="Test Sana")
    order = make_order(db_session, customer)
    make_workflow(db_session, steps=[
        {"type": "create_task", "params": {"title": "Phone Test Sana", "dueInHours": 2}},
        {"type": "notify", "params": {"title": "Big order"}},
        {"type": "add_tag", "params": {"tag": "VIP"}},
        {"type": "remove_tag", "params": {"tag": "vip"}},
        {"type": "update_order_status", "params": {"status": "dispatched"}},
    ])
    engine.emit(db_session, settings(), "order_created", {"order_id": order.id, "customer_id": customer.id}, "k4", NOON)
    for _ in range(6):
        engine.run_due_jobs(db_session, settings(), NOON)
    assert db_session.query(WorkflowRun).one().status == "done"
    assert sorted(t.kind for t in db_session.query(Task)) == ["notification", "task"]
    assert db_session.get(Customer, customer.id).tags == []
    from app.services import order_status

    assert order_status.latest_status(db_session, order.id).status == "dispatched"


def test_an_invalid_status_step_fails_that_step_only_and_not_the_order(db_session):
    from app.services import order_status

    customer = make_customer(db_session)
    order = make_order(db_session, customer)
    order_status.record_status(db_session, settings(), order, "delivered", source="manual", notify=False, now=NOON, at=NOON)
    make_workflow(db_session, steps=[{"type": "update_order_status", "params": {"status": "dispatched"}}, {"type": "notify", "params": {"title": "never reached"}}])
    engine.emit(db_session, settings(), "order_created", {"order_id": order.id, "customer_id": customer.id}, "k5", NOON)
    engine.run_due_jobs(db_session, settings(), NOON)
    job = db_session.query(Job).one()
    assert (job.status, job.last_error) == ("failed", "invalid_transition")
    assert db_session.query(WorkflowRun).one().status == "failed" and db_session.query(Task).count() == 0
    assert order_status.latest_status(db_session, order.id).status == "delivered"             # the order is untouched


def test_a_web_address_must_be_approved(db_session):
    customer = make_customer(db_session)
    order = make_order(db_session, customer)
    make_workflow(db_session, steps=[{"type": "call_webhook", "params": {"url": "https://hooks.example/test"}}])
    engine.emit(db_session, settings(), "order_created", {"order_id": order.id, "customer_id": customer.id}, "k6", NOON)
    engine.run_due_jobs(db_session, settings(), NOON)
    assert db_session.query(Job).one().last_error == "webhook_not_approved"
    assert wf_actions.allowed_webhooks(settings(workflow_webhook_urls="https://a.example/x, http://b.example")) == {"https://a.example/x"}


# --- failures, retries, recovery, loops ----------------------------------------------------------------------------------------


def test_a_failing_step_is_retried_with_growing_waits_then_fails_for_good_and_can_be_retried(db_session, monkeypatch):
    customer = make_customer(db_session)
    order = make_order(db_session, customer)
    make_workflow(db_session)
    engine.emit(db_session, settings(), "order_created", {"order_id": order.id, "customer_id": customer.id}, "k7", NOON)

    def boom(*a, **k):
        raise RuntimeError("temporary trouble")

    monkeypatch.setattr(wf_actions, "perform", boom)
    now = NOON
    waits = []
    for _ in range(4):
        engine.run_due_jobs(db_session, settings(), now)
        job = db_session.query(Job).one()
        if job.status == "pending":
            waits.append(int((job.run_at - now).total_seconds() // 60))
            now = job.run_at
    assert waits == [5, 10, 20]                                                               # 5, 10, 20 minutes
    job = db_session.query(Job).one()
    assert (job.status, job.attempts) == ("failed", 4) and "temporary trouble" in job.last_error
    assert db_session.query(WorkflowRun).one().status == "failed"
    monkeypatch.undo()
    engine.retry_job(db_session, job.id, now)
    engine.run_due_jobs(db_session, settings(), now)
    assert db_session.query(Job).one().status == "done" and db_session.query(WorkflowRun).one().status == "done"


def test_a_job_left_running_by_a_dead_worker_is_picked_up_again(db_session):
    customer = make_customer(db_session)
    order = make_order(db_session, customer)
    make_workflow(db_session)
    engine.emit(db_session, settings(), "order_created", {"order_id": order.id, "customer_id": customer.id}, "k8", NOON)
    job = db_session.query(Job).one()
    job.status, job.started_at = "running", NOON                                              # the worker died here
    db_session.flush()
    assert engine.run_due_jobs(db_session, settings(), NOON + timedelta(minutes=5))["done"] == 0       # still within the grace time
    counts = engine.run_due_jobs(db_session, settings(), NOON + timedelta(minutes=20))
    assert counts["recovered"] == 1 and counts["done"] == 1


def test_paused_workflows_hold_their_waiting_steps_and_cancel_stops_a_run(db_session):
    customer = make_customer(db_session)
    order = make_order(db_session, customer)
    w = make_workflow(db_session)
    engine.emit(db_session, settings(), "order_created", {"order_id": order.id, "customer_id": customer.id}, "k9", NOON)
    w.enabled = False
    db_session.flush()
    engine.run_due_jobs(db_session, settings(), NOON)
    assert db_session.query(Job).one().status == "pending"                                    # paused: held
    w.enabled = True
    run = db_session.query(WorkflowRun).one()
    engine.cancel_run(db_session, run.id, NOON)
    engine.run_due_jobs(db_session, settings(), NOON)
    assert db_session.query(Job).one().status == "cancelled" and run.status == "cancelled"


def test_a_workflow_cannot_trigger_itself(db_session):
    customer = make_customer(db_session)
    order = make_order(db_session, customer)
    # "when an order changes status, move it forward": without protection this would chain forever
    loop = make_workflow(db_session, trigger="order_status_changed", steps=[{"type": "update_order_status", "params": {"status": "dispatched"}}], name="loop")
    other = make_workflow(db_session, trigger="order_status_changed", steps=[{"type": "add_tag", "params": {"tag": "seen"}}], name="other")
    engine.emit(db_session, settings(), "order_status_changed", {"order_id": order.id, "customer_id": customer.id, "status": "confirmed"}, "k10", NOON)
    for _ in range(8):
        engine.run_due_jobs(db_session, settings(), NOON)
    runs = db_session.query(WorkflowRun).filter(WorkflowRun.workflow_id == loop.id).all()
    assert len(runs) == 1                                                                     # the status change it made did not start it again
    assert db_session.query(WorkflowRun).filter(WorkflowRun.workflow_id == other.id).count() == 2      # but another workflow may react to it (confirmed, then dispatched)


# --- hooks and the clock ----------------------------------------------------------------------------------------------------------


def test_a_status_change_in_the_app_starts_a_workflow(db_session):
    from app.services import order_status

    customer = make_customer(db_session)
    order = make_order(db_session, customer)
    make_workflow(db_session, trigger="order_status_changed", conditions_={"rules": [rule("order_status", "eq", "returned")]}, steps=[{"type": "create_task", "params": {"title": "Check the return"}}])
    now = datetime.now(timezone.utc)
    order_status.record_status(db_session, settings(), order, "confirmed", source="manual", notify=False, now=now, at=now)
    assert db_session.query(WorkflowRun).count() == 0
    order_status.record_status(db_session, settings(), order, "returned", source="manual", notify=False, now=now, at=now)
    assert db_session.query(WorkflowRun).count() == 1


def test_an_engine_error_never_breaks_the_order_status(db_session, monkeypatch):
    from app.services import order_status
    from app.services.workflows import facts

    customer = make_customer(db_session)
    order = make_order(db_session, customer)
    make_workflow(db_session, trigger="order_status_changed")
    monkeypatch.setattr(facts, "build", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("broken workflow")))
    now = datetime.now(timezone.utc)
    change = order_status.record_status(db_session, settings(), order, "confirmed", source="manual", notify=False, now=now, at=now)
    assert change.recorded and order_status.latest_status(db_session, order.id).status == "confirmed"


def test_the_daily_tick_fires_schedule_workflows_once_a_day_and_finds_inactive_customers(db_session):
    customer = make_customer(db_session)
    make_order(db_session, customer)                                                          # ordered on 2026-03-09
    make_workflow(db_session, trigger="schedule_daily", steps=[{"type": "notify", "params": {"title": "Good morning"}}], name="daily")
    make_workflow(db_session, trigger="customer_inactive", config={"days": 30}, steps=[{"type": "create_task", "params": {"title": "Win back"}}], name="inactive")
    early = datetime(2026, 3, 20, 7, 0, tzinfo=timezone.utc)
    assert engine.tick(db_session, settings(), early)["inactive"] == 0                         # only 11 days of silence
    late = datetime(2026, 5, 1, 7, 0, tzinfo=timezone.utc)
    first = engine.tick(db_session, settings(), late)
    assert first["daily"] == 1 and first["inactive"] == 1
    again = engine.tick(db_session, settings(), late + timedelta(hours=1))
    assert again["daily"] == 0 and again["inactive"] == 0                                      # not twice the same day, not twice for the same silence


def test_a_low_stock_workflow_fires_when_stock_falls_to_the_warning_level(db_session):
    from app.models.inventory import StockItem
    from app.services import inventory

    item = StockItem(sku="TST-W", name="Test cap", stock=10, reorder_threshold=3)
    db_session.add(item)
    db_session.flush()
    make_workflow(db_session, trigger="stock_below_threshold", steps=[{"type": "notify", "params": {"title": "Reorder caps"}}])
    inventory.adjust(db_session, item.id, -5, "adjustment", None)           # 5 left: above the warning level
    assert db_session.query(WorkflowRun).count() == 0
    inventory.adjust(db_session, item.id, -3, "adjustment", None)           # 2 left: fires
    inventory.adjust(db_session, item.id, -1, "adjustment", None)           # already low: does not fire again
    assert db_session.query(WorkflowRun).count() == 1


# --- dry run and the API -----------------------------------------------------------------------------------------------------------


def test_dry_run_shows_what_would_happen_and_changes_nothing(db_session):
    customer = make_customer(db_session)
    order = make_order(db_session, customer, value=7000)
    definition = {"conditions": {"rules": [rule("order_total", "gt", 5000)]}, "actions": [
        {"type": "add_tag", "params": {"tag": "big"}}, {"type": "send_message", "params": {"channel": "whatsapp", "event": "order_confirmed"}},
        {"type": "call_webhook", "params": {"url": "https://x.example/h"}}]}
    result = engine.dry_run(db_session, settings(), definition, {"order_id": order.id, "customer_id": customer.id})
    assert result["matched"] is True and result["trace"][0]["actual"] == 7000.0
    assert "Would add the tag" in result["steps"][0]["wouldDo"] and "Would fail: no_template" in result["steps"][1]["wouldDo"] and "not in the approved list" in result["steps"][2]["wouldDo"]
    assert db_session.get(Customer, customer.id).tags == [] and db_session.query(WorkflowRun).count() == 0 and db_session.query(Message).count() == 0
    miss = engine.dry_run(db_session, settings(), {**definition, "conditions": {"rules": [rule("order_total", "gt", 99999)]}}, {"order_id": order.id})
    assert miss["matched"] is False and miss["steps"] == []


def test_api_build_validate_test_enable_and_read_the_log(db_client, db_session):
    meta = db_client.get("/api/v1/workflows/meta").json()
    assert {t["id"] for t in meta["triggers"]} >= {"order_created", "schedule_daily"} and meta["limits"]["maxActions"] == spec.MAX_ACTIONS
    bad = {"name": "Bad", "trigger": "order_created", "actions": []}
    assert db_client.post("/api/v1/workflows/validate", json=bad).json()["valid"] is False
    assert db_client.post("/api/v1/workflows", json=bad).status_code == 422
    good = {"name": "Tag big orders", "trigger": "order_created", "conditions": {"op": "and", "rules": [rule("order_total", "gt", 5000)]},
            "actions": [{"type": "add_tag", "params": {"tag": "big"}, "delayMinutes": 0}]}
    created = db_client.post("/api/v1/workflows", json=good)
    assert created.status_code == 201 and created.json()["enabled"] is False and created.json()["version"] == 1
    wid = created.json()["id"]
    customer = make_customer(db_session)
    order = make_order(db_session, customer, value=9000)
    db_session.commit()
    tested = db_client.post("/api/v1/workflows/test", json={"definition": good, "orderId": order.id})
    assert tested.status_code == 200 and tested.json()["matched"] is True
    assert db_client.put(f"/api/v1/workflows/{wid}", json={**good, "name": "Renamed"}).json()["version"] == 1       # name only: same version
    changed = {**good, "actions": [{"type": "add_tag", "params": {"tag": "huge"}}]}
    assert db_client.put(f"/api/v1/workflows/{wid}", json=changed).json()["version"] == 2
    assert db_client.post(f"/api/v1/workflows/{wid}/enable").json()["enabled"] is True
    engine.emit(db_session, settings(), "order_created", {"order_id": order.id, "customer_id": customer.id}, "api1", NOON)
    db_session.commit()
    assert db_client.post("/api/v1/workflows/run-due").json()["done"] >= 0
    runs = db_client.get("/api/v1/workflows/runs/list").json()
    assert len(runs) == 1 and runs[0]["workflowVersion"] == 2
    detail = db_client.get(f"/api/v1/workflows/runs/{runs[0]['id']}").json()
    assert detail["jobs"][0]["actionType"] == "add_tag" and detail["context"]["facts"]["order_total"] == 9000.0
    assert db_client.get("/api/v1/workflows/jobs/failed").json() == []
    assert db_client.post(f"/api/v1/workflows/{wid}/disable").json()["enabled"] is False
    assert db_client.delete(f"/api/v1/workflows/{wid}").status_code == 204
