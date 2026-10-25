"""Leads: sources, duplicates, the pipeline, the 24-hour alert, converting to a customer, and the public/Meta entrances.
All people are made up (marked TEST)."""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.main import app
from app.models import Customer, Task
from app.models.lead import Lead, LeadEvent
from app.services import leads
from app.services.messaging import webhook
from app.services.rate_limit import reset_rate_limits

NOW = datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc)


def settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def new_lead(db, **kw):
    kw.setdefault("source", "manual")
    kw.setdefault("phone", "0300 1234567")
    kw.setdefault("name", "Test Lead")
    return leads.create_lead(db, **kw)[0]


def test_a_lead_needs_a_usable_phone_or_email(db_session):
    with pytest.raises(ApiError):
        leads.create_lead(db_session, source="manual", name="Nobody", phone="12345")
    assert leads.create_lead(db_session, source="manual", email="test.lead@testcustomer.test")[1] is True


def test_the_same_open_phone_is_one_lead_and_the_same_meta_lead_is_one_lead(db_session):
    first = new_lead(db_session, phone="03001234567")
    again, created = leads.create_lead(db_session, source="website_form", phone="+92 300 1234567")
    assert created is False and again.id == first.id
    m1, c1 = leads.create_lead(db_session, source="meta_lead_ad", phone="03007654321", external_ref="meta:1")
    m2, c2 = leads.create_lead(db_session, source="meta_lead_ad", phone="03009999999", external_ref="meta:1")
    assert (c1, c2, m1.id) == (True, False, m2.id)


def test_stage_changes_follow_the_pipeline(db_session):
    lead = new_lead(db_session)
    with pytest.raises(ApiError) as caught:
        leads.move(db_session, lead, "new")
    assert caught.value.code == "same_stage"
    leads.move(db_session, lead, "contacted", now=NOW)
    assert lead.contacted_at == NOW
    leads.move(db_session, lead, "interested", follow_up_at=NOW + timedelta(hours=5))
    assert db_session.query(Task).filter(Task.title.like("Follow up%")).count() == 1
    leads.move(db_session, lead, "lost", lost_reason="too expensive")
    assert lead.lost_reason == "too expensive" and lead.follow_up_at is None
    with pytest.raises(ApiError) as caught:
        leads.move(db_session, lead, "converted")
    assert caught.value.code == "invalid_transition"                                          # lost leads must be reopened first
    leads.move(db_session, lead, "new")
    assert lead.stage == "new" and lead.lost_reason is None
    events = [e.event for e in db_session.query(LeadEvent).filter_by(lead_id=lead.id).order_by(LeadEvent.id)]
    assert events == ["created", "moved", "moved", "moved", "moved"]


def test_a_lead_not_contacted_in_time_alerts_once(db_session):
    lead = new_lead(db_session)
    lead.created_at = NOW - timedelta(hours=30)
    fresh = new_lead(db_session, phone="0301 1111111")
    fresh.created_at = NOW - timedelta(hours=2)
    db_session.flush()
    assert leads.check_sla(db_session, settings(), NOW) == {"sla_alerts": 1}
    assert leads.check_sla(db_session, settings(), NOW + timedelta(hours=1)) == {"sla_alerts": 0}      # once, not every hour
    assert db_session.query(Task).filter(Task.kind == "notification").count() == 1
    assert lead.sla_alerted is True and fresh.sla_alerted is False
    assert leads.check_sla(db_session, settings(lead_sla_hours=1), NOW) == {"sla_alerts": 1}           # the deadline is a setting


def test_converting_links_an_existing_customer_without_losing_history(db_session):
    customer = Customer(external_id="TEST-LC1", first_name="Test", phone="+923001234567", phone_normalised="+923001234567")
    db_session.add(customer)
    db_session.flush()
    lead = new_lead(db_session, phone="03001234567", source="website_form", utm_source="instagram")
    leads.move(db_session, lead, "converted")
    assert lead.customer_id == customer.id and lead.stage == "converted"
    assert customer.acquisition_source == "website form"
    assert lead.utm_source == "instagram" and db_session.query(LeadEvent).filter_by(lead_id=lead.id, event="converted").one().detail["new_customer"] is False


def test_converting_a_stranger_makes_a_customer_with_no_marketing_consent(db_session):
    from app.services.messaging import consent

    lead = new_lead(db_session, phone="03005550001", name="Test Sara Khan")
    leads.convert(db_session, lead)
    customer = db_session.get(Customer, lead.customer_id)
    assert (customer.first_name, customer.last_name, customer.phone_normalised) == ("Test", "Sara Khan", "+923005550001")
    assert consent.consent_state(db_session, customer.id, "whatsapp") != "opted_in"
    with pytest.raises(ApiError):
        leads.convert(db_session, lead)


def test_meta_instant_form_answers_become_a_lead(db_session):
    fields = [{"name": "full_name", "values": ["Test Meta Person"]}, {"name": "phone_number", "values": ["+923004443322"]}, {"name": "email", "values": ["test.meta@testcustomer.test"]},
              {"name": "which_product", "values": ["Leather wallet"]}]
    lead, created = leads.from_meta_fields(db_session, "L100", fields, campaign="Eid wallets")
    assert created and (lead.source, lead.name, lead.phone_normalised, lead.product_interest, lead.campaign) == ("meta_lead_ad", "Test Meta Person", "+923004443322", "Leather wallet", "Eid wallets")
    assert leads.from_meta_fields(db_session, "L100", fields)[1] is False


def test_click_to_whatsapp_from_a_stranger_makes_a_lead_but_a_plain_message_does_not(db_session):
    def payload(wamid, referral):
        message = {"id": wamid, "from": "923006667788", "type": "text", "timestamp": "1773000100", "text": {"body": "Price of the wallet?"}}
        if referral:
            message["referral"] = {"headline": "Eid wallet sale", "source_url": "https://fb.me/ad1"}
        return {"entry": [{"changes": [{"value": {"contacts": [{"wa_id": "923006667788", "profile": {"name": "Test Ad Clicker"}}], "messages": [message]}}]}]}

    webhook.process_whatsapp_payload(db_session, payload("wamid.LEAD0", False), NOW)
    assert db_session.query(Lead).count() == 0
    webhook.process_whatsapp_payload(db_session, payload("wamid.LEAD1", True), NOW)
    lead = db_session.query(Lead).one()
    assert (lead.source, lead.name, lead.campaign, lead.product_interest) == ("click_to_whatsapp", "Test Ad Clicker", "Eid wallet sale", "Price of the wallet?")


def test_a_new_lead_can_start_a_workflow(db_session):
    from app.models import Workflow, WorkflowRun

    db_session.add(Workflow(name="Test lead alert", trigger="lead_created", enabled=True, conditions={"rules": [{"field": "lead_source", "operator": "eq", "value": "manual"}]},
                            actions=[{"type": "notify", "params": {"title": "New lead"}}]))
    db_session.flush()
    new_lead(db_session)
    assert db_session.query(WorkflowRun).count() == 1


# --- over HTTP --------------------------------------------------------------------------------------------------------------


def test_api_pipeline(db_client, db_session):
    r = db_client.post("/api/v1/leads", json={"name": "Test Api", "phone": "0302 2223344", "productInterest": "Mug", "utmSource": "facebook"})
    assert r.status_code == 201 and r.json()["stage"] == "new" and r.json()["allowedNext"] == ["contacted", "interested", "converted", "lost"]
    lead_id = r.json()["id"]
    assert db_client.post("/api/v1/leads", json={"phone": "0302 2223344"}).status_code == 409
    assert db_client.post(f"/api/v1/leads/{lead_id}/move", json={"stage": "converted"}).json()["customerId"] is not None
    assert db_client.post(f"/api/v1/leads/{lead_id}/move", json={"stage": "lost"}).status_code == 409
    summary = db_client.get("/api/v1/leads/summary").json()
    assert summary["stages"]["converted"] == 1 and summary["slaHours"] == 24
    assert [e["event"] for e in db_client.get(f"/api/v1/leads/{lead_id}/events").json()][-1] == "created"
    test = db_client.post("/api/v1/leads/meta/test", json={"leadgenId": "T1", "fieldData": [{"name": "phone_number", "values": ["03008887766"]}]})
    assert test.status_code == 201 and test.json()["source"] == "meta_lead_ad"
    assert db_client.get("/api/v1/leads?stage=converted").json()[0]["id"] == lead_id


@pytest.fixture
def public_form(db_client):
    reset_rate_limits()
    app.dependency_overrides[get_settings] = lambda: settings(public_leads_enabled=True)
    yield db_client
    reset_rate_limits()


def test_the_public_form_is_off_by_default(db_client):
    assert db_client.post("/api/v1/public/leads", json={"phone": "03001230000"}).status_code == 404


def test_the_public_form_saves_a_lead_ignores_bots_and_is_rate_limited(public_form, db_session):
    ok = public_form.post("/api/v1/public/leads", json={"name": "Test Visitor", "phone": "0300 1230000", "utmSource": "google", "message": "Do you have size 9?"})
    assert ok.status_code == 200 and db_session.query(Lead).one().source == "website_form"
    assert public_form.post("/api/v1/public/leads", json={"phone": "0300 1239999", "website": "http://spam.example"}).status_code == 200
    assert db_session.query(Lead).count() == 1                                                  # the bot's lead was thrown away
    assert public_form.post("/api/v1/public/leads", json={"name": "No contact"}).status_code == 422
    codes = [public_form.post("/api/v1/public/leads", json={"phone": f"03001{i:06d}"}).status_code for i in range(12)]
    assert 429 in codes


def sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_the_meta_leads_webhook_needs_a_valid_signature(db_client, db_session, monkeypatch):
    app.dependency_overrides[get_settings] = lambda: settings(whatsapp_app_secret="test-app-secret", meta_page_token="test-page-token")
    monkeypatch.setattr(leads, "fetch_meta_lead", lambda s, lid: {"field_data": [{"name": "phone_number", "values": ["03004445566"]}, {"name": "full_name", "values": ["Test Webhook"]}]})
    body = json.dumps({"entry": [{"changes": [{"field": "leadgen", "value": {"leadgen_id": "WH1", "ad_id": "ad-77"}}]}]}).encode()
    assert db_client.post("/api/v1/webhooks/meta-leads", content=body).status_code == 403
    assert db_client.post("/api/v1/webhooks/meta-leads", content=body, headers={"x-hub-signature-256": sign(body, "wrong")}).status_code == 403
    ok = db_client.post("/api/v1/webhooks/meta-leads", content=body, headers={"x-hub-signature-256": sign(body, "test-app-secret")})
    assert ok.status_code == 200 and ok.json()["saved"] == 1 and db_session.query(Lead).one().campaign == "ad-77"
    again = db_client.post("/api/v1/webhooks/meta-leads", content=body, headers={"x-hub-signature-256": sign(body, "test-app-secret")})
    assert again.json()["saved"] == 0 and db_session.query(Lead).count() == 1                     # Meta retrying does not duplicate


def test_without_a_page_token_the_real_fetch_says_so_instead_of_pretending():
    with pytest.raises(ApiError) as caught:
        leads.fetch_meta_lead(settings(), "X")
    assert caught.value.code == "meta_not_configured"
