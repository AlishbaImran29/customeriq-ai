"""Meta Ads: hashing the way Meta asks, consent, test mode, delivered-only purchases, ad spend import, true ROAS.
Everything is made up (marked TEST); NO network call is ever made (Meta is replaced by a fake)."""

import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import AdSpend, Customer
from app.models.meta_event import MetaEvent
from app.services import meta_ads as ma
from tests.test_order_status import NOON, make_customer, make_order, opt_in, record

TODAY = date(2026, 3, 10)


def settings(**kw) -> Settings:
    base = dict(meta_ads_dry_run=True)
    return Settings(_env_file=None, **{**base, **kw})


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def person(db, phone="+923001234567", email="Test.Meta@Example.com", agree=True):
    c = make_customer(db, phone=phone, email=email)
    if agree:
        opt_in(db, c)
    return c


def test_hashing_follows_metas_rules():
    assert ma.hash_email("  Test.Meta@Example.COM ") == sha("test.meta@example.com")
    assert ma.hash_phone("0300 1234567") == sha("923001234567")                      # country code, digits only, no plus
    assert ma.hash_phone("+92 300 1234567") == sha("923001234567")
    assert ma.hash_email("not an email") is None and ma.hash_phone("123") is None and ma.hash_email(None) is None


def test_only_customers_who_agreed_and_have_a_contact_are_in_an_audience(db_session):
    person(db_session, phone="+923001111111", email="agreed@test.example")
    person(db_session, phone="+923002222222", email="never.agreed@test.example", agree=False)
    c = make_customer(db_session, phone="+923003333333", email=None)
    opt_in(db_session, c)
    for who in db_session.query(Customer):
        make_order(db_session, who)
    rows, left_out = ma.audience_rows(db_session, "buyers")
    assert sorted(r[0] for r in rows) == sorted([sha("agreed@test.example"), ""]) and left_out == 1
    assert [sha("923001111111"), sha("923003333333")] == sorted(r[1] for r in rows) or {r[1] for r in rows} == {sha("923001111111"), sha("923003333333")}


def test_the_payload_has_the_schema_meta_expects(db_session):
    payload = ma.user_payload([["a" * 64, ""]])
    assert payload == {"schema": ["EMAIL_SHA256", "PHONE_SHA256"], "data": [["a" * 64, ""]]}


def test_test_mode_prepares_the_audience_but_sends_nothing(db_session, monkeypatch):
    c = person(db_session)
    make_order(db_session, c)
    monkeypatch.setattr(ma, "_call", lambda *a, **k: pytest.fail("test mode must not call Meta"))
    result = ma.push_audience(db_session, settings(), "buyers", "Test audience")
    assert result["dryRun"] is True and result["customers"] == 1 and result["audienceId"] is None and result["sample"][0][0].endswith("…")
    empty = person(db_session, phone="+923004444444", email="nobody@test.example", agree=False)
    make_order(db_session, empty)
    db_session.query(MetaEvent).delete()


def test_a_real_push_creates_the_audience_then_uploads_in_batches(db_session, monkeypatch):
    c = person(db_session)
    make_order(db_session, c)
    calls = []

    def fake(settings_, method, path, params):
        calls.append((method, path, params))
        return {"id": "AUD1"} if path.endswith("customaudiences") else {"num_received": 1}

    monkeypatch.setattr(ma, "_call", fake)
    live = settings(meta_ads_dry_run=False, meta_ads_access_token="test-token", meta_ad_account_id="999")
    result = ma.push_audience(db_session, live, "buyers", "Test audience")
    assert result["audienceId"] == "AUD1" and [c_[1] for c_ in calls] == ["act_999/customaudiences", "AUD1/users"]
    assert calls[0][2]["customer_file_source"] == "USER_PROVIDED_ONLY" and '"EMAIL_SHA256"' in calls[1][2]["payload"] and "Test.Meta" not in calls[1][2]["payload"]


def test_an_empty_audience_is_refused_not_sent(db_session):
    with pytest.raises(ApiError) as caught:
        ma.push_audience(db_session, settings(), "champions", "x")
    assert caught.value.code == "empty_audience"
    with pytest.raises(ApiError):
        ma.audience_rows(db_session, "everyone")


def test_meta_errors_become_clear_messages(monkeypatch):
    import io
    import urllib.error

    def boom(request, timeout):
        raise urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(b'{"error": {"code": 2663, "message": "x"}}'))

    monkeypatch.setattr(ma.urllib.request, "urlopen", boom)
    with pytest.raises(ApiError) as caught:
        ma._call(settings(meta_ads_access_token="secret-token"), "POST", "act_1/customaudiences", {})
    assert caught.value.status_code == 502 and "Terms" in caught.value.message and "secret-token" not in caught.value.message
    with pytest.raises(ApiError) as caught:
        ma._call(settings(), "GET", "x", {})
    assert caught.value.code == "meta_not_configured"


# --- delivered-only purchases ----------------------------------------------------------------------------------------------------


def test_a_purchase_is_queued_when_the_order_is_delivered_not_when_it_is_placed(db_session):
    c = person(db_session)
    order = make_order(db_session, c, value=2500)
    record(db_session, order, "confirmed", notify=False)
    record(db_session, order, "dispatched", notify=False)
    assert db_session.query(MetaEvent).count() == 0                                           # placing and shipping send nothing
    record(db_session, order, "delivered", notify=False)
    record(db_session, order, "returned", notify=False)
    events = db_session.query(MetaEvent).all()
    assert [e.event_id for e in events] == [f"purchase-{order.id}"] and events[0].status == "pending"
    assert ma.queue_purchase(db_session, order).id == events[0].id                            # an order is never queued twice


def test_pending_events_are_sent_once_with_a_dedupe_id_and_hashed_details(db_session, monkeypatch):
    c = person(db_session)
    order = make_order(db_session, c, value=2500)
    ma.queue_purchase(db_session, order, NOON)
    sent = []
    monkeypatch.setattr(ma, "_call", lambda s, m, path, params: sent.append((path, params)) or {"events_received": 1})
    live = settings(meta_ads_dry_run=False, meta_ads_access_token="t", meta_pixel_id="PIX1")
    assert ma.send_pending(db_session, live, NOON)["sent"] == 1
    assert ma.send_pending(db_session, live, NOON)["sent"] == 0                               # the second run finds nothing to send
    path, params = sent[0]
    assert path == "PIX1/events"
    assert '"event_name": "Purchase"' in params["data"] and f'"event_id": "purchase-{order.id}"' in params["data"] and '"value": 2500.0' in params["data"]
    assert "Test.Meta" not in params["data"] and sha("test.meta@example.com") in params["data"] and "923001234567" not in params["data"].replace(sha("923001234567"), "")


def test_test_mode_logs_the_event_as_dry_run_and_sends_nothing(db_session, monkeypatch):
    c = person(db_session)
    ma.queue_purchase(db_session, make_order(db_session, c), NOON)
    monkeypatch.setattr(ma, "_call", lambda *a, **k: pytest.fail("test mode must not call Meta"))
    assert ma.send_pending(db_session, settings(), NOON)["dry_run"] == 1
    assert db_session.query(MetaEvent).one().status == "dry_run"


def test_customers_who_never_agreed_are_skipped(db_session):
    c = person(db_session, agree=False)
    ma.queue_purchase(db_session, make_order(db_session, c), NOON)
    assert ma.send_pending(db_session, settings(), NOON)["skipped"] == 1
    event = db_session.query(MetaEvent).one()
    assert (event.status, event.error) == ("skipped", "no_consent")


def test_a_failing_send_is_retried_then_marked_failed(db_session, monkeypatch):
    c = person(db_session)
    ma.queue_purchase(db_session, make_order(db_session, c), NOON)
    monkeypatch.setattr(ma, "_call", lambda *a, **k: (_ for _ in ()).throw(ApiError(502, "meta_error", "Meta refused")))
    live = settings(meta_ads_dry_run=False, meta_ads_access_token="t", meta_pixel_id="PIX1")
    for _ in range(ma.MAX_ATTEMPTS):
        ma.send_pending(db_session, live, NOON)
    event = db_session.query(MetaEvent).one()
    assert (event.status, event.attempts, event.error) == ("failed", ma.MAX_ATTEMPTS, "Meta refused")


# --- ad spend and true ROAS --------------------------------------------------------------------------------------------------------


CSV = b"Date,Campaign,Channel,Amount,Purchases,Purchase value\n2026-03-10,Eid sale,facebook,\"1,500\",4,12000\n10/03/2026,Eid sale,instagram,500,,\nbad,x,facebook,1,,\n2026-03-11,Eid sale,facebook,-5,,\n"


def test_ad_spend_csv_is_validated_and_importing_twice_changes_nothing(db_session):
    first = ma.import_spend_csv(db_session, CSV)
    assert (first.added, first.updated, first.rejected) == (2, 0, 2) and len(first.errors) == 2
    again = ma.import_spend_csv(db_session, CSV)
    assert (again.added, again.updated) == (0, 2) and db_session.query(AdSpend).count() == 2
    row = db_session.query(AdSpend).filter_by(channel="facebook").one()
    assert (row.amount, row.meta_purchases, row.meta_revenue, row.source) == (Decimal("1500"), 4, Decimal("12000"), "csv")
    with pytest.raises(ApiError) as caught:
        ma.import_spend_csv(db_session, b"day,cost\n1,2\n")
    assert caught.value.code == "missing_column"
    with pytest.raises(ApiError):
        ma.import_spend_csv(db_session, b"x" * (ma.MAX_CSV_BYTES + 1))


def test_marketing_api_insights_are_parsed():
    rows = ma.parse_insights({"data": [
        {"date_start": "2026-03-10", "campaign_name": "Eid sale", "spend": "1500.50", "actions": [{"action_type": "purchase", "value": "4"}], "action_values": [{"action_type": "purchase", "value": "12000"}]},
        {"date_start": "2026-03-11", "campaign_name": "Other", "spend": "10"},
        {"date_start": "broken", "spend": "1"},
    ]})
    assert rows == [(date(2026, 3, 10), "Eid sale", Decimal("1500.50"), 4, Decimal("12000")), (date(2026, 3, 11), "Other", Decimal("10"), None, None)]


def test_true_roas_uses_only_delivered_revenue_and_hides_ratios_for_small_numbers(db_session):
    from app.models import Order

    c = person(db_session)
    db_session.add(AdSpend(spend_date=TODAY, channel="facebook", campaign="Eid sale", amount=Decimal(1000), meta_purchases=3, meta_revenue=Decimal(9000), source="csv"))
    delivered = make_order(db_session, c, value=2000)
    returned = make_order(db_session, c, value=3000)
    untagged = make_order(db_session, c, value=500)
    for o, tag, outcome in ((delivered, "eid SALE", "delivered"), (returned, "Eid sale", "returned"), (untagged, None, "delivered")):
        o.order_date, o.utm_campaign, o.outcome = TODAY, tag, outcome
    db_session.flush()
    rows, untagged_count = ma.roas(db_session, TODAY, TODAY)
    r = rows[0]
    assert (r.campaign, r.orders, r.delivered, r.returned, r.real_revenue, untagged_count) == ("Eid sale", 2, 1, 1, Decimal(2000), 1)
    assert r.meta_roas == pytest.approx(9.0)                                                  # Meta says 9x...
    assert r.true_roas is None and r.enough is False                                          # ...the real ratio is hidden until there are enough orders
    assert db_session.get(Order, delivered.id).utm_campaign == "eid SALE"


def test_shopify_orders_carry_the_campaign_from_the_landing_link(db_session):
    from app.services import shopify_hooks

    payload = {"id": 4242, "name": "#4242", "total_price": "1000", "created_at": NOON.isoformat(), "email": "shopper@test.example", "phone": "+923005551234",
               "landing_site": "/products/shoes?utm_source=facebook&utm_campaign=Eid%20sale", "line_items": [{"title": "Test shoes", "quantity": 1}]}
    order = shopify_hooks.upsert_order(db_session, payload)
    assert (order.utm_source, order.utm_campaign) == ("facebook", "Eid sale")


def test_api_status_preview_push_and_roas(db_client, db_session):
    c = person(db_session)
    make_order(db_session, c)
    db_session.commit()
    status = db_client.get("/api/v1/meta-ads/status").json()
    assert status["testMode"] is True and status["readyToSend"] is False and len(status["setupSteps"]) == 5
    preview = db_client.post("/api/v1/meta-ads/audiences/preview", json={"segment": "buyers"}).json()
    assert preview["customers"] == 1 and "SHA-256" in preview["rule"]
    assert db_client.post("/api/v1/meta-ads/audiences/push", json={"segment": "buyers"}).status_code == 422             # needs confirm
    pushed = db_client.post("/api/v1/meta-ads/audiences/push", json={"segment": "buyers", "confirm": True}).json()
    assert pushed["dryRun"] is True and pushed["audienceId"] is None
    imported = db_client.post("/api/v1/meta-ads/ad-spend/import", files={"file": ("spend.csv", CSV, "text/csv")})
    assert imported.status_code == 200 and imported.json()["added"] == 2
    assert db_client.get("/api/v1/meta-ads/roas?start=2026-03-01&end=2026-03-31").json()["campaigns"][0]["spend"] == 2000.0
    assert db_client.get("/api/v1/meta-ads/roas?start=2026-03-31&end=2026-03-01").status_code == 422
    assert db_client.get("/api/v1/meta-ads/events/summary").json()["pending"] == 0
    assert db_client.post("/api/v1/meta-ads/ad-spend/sync").status_code == 503                                          # no token: honest message


def test_staff_cannot_push_audiences_or_send_events(db_client):
    import uuid
    from types import SimpleNamespace

    from app.api.deps import require_user
    from app.main import app

    app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=uuid.uuid4(), email="staff@test.example", name="S", role="staff")
    assert db_client.post("/api/v1/meta-ads/audiences/push", json={"segment": "buyers", "confirm": True}).status_code == 403
    assert db_client.post("/api/v1/meta-ads/events/send").status_code == 403
    assert db_client.post("/api/v1/meta-ads/audiences/preview", json={"segment": "buyers"}).status_code == 200            # a preview changes nothing
