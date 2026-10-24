"""Auto Messenger part 4: product announcements. Customers, products, segments and AI answers are made up (TEST)."""

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.main import app
from app.models import Campaign, CampaignRecipient, CatalogProduct, Customer, LaunchProject, Message, MessageTemplate, Order
from app.services import launch_ai, shopify_hooks
from app.services.messaging import campaign_ai, campaigns, consent
from app.services.messaging.settings_store import get_row

NOW = datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc)                   # 12:00 in Pakistan: not in quiet hours
_n = [0]


def settings(**changes) -> Settings:
    return Settings(_env_file=None, messaging_dry_run=True, **changes)


def customer(db, *, name="Test Ali", phone=None, email=None, wa=True, mail=False, language=None, category="Shoes", products="Test shoes"):
    _n[0] += 1
    phone = phone or f"+92300{_n[0]:07d}"
    c = Customer(external_id=f"TEST-CP{_n[0]}", first_name=name, phone=phone, phone_normalised=phone, email=email or f"cp{_n[0]}.test@testcustomer.test", country="Pakistan", preferred_language=language)
    db.add(c)
    db.flush()
    db.add(Order(external_id=f"TEST-CPO-{_n[0]}", customer_id=c.id, order_date=date(2026, 2, 1), order_value=Decimal(1500), product_category=category, products=products, source="manual"))
    if wa:
        consent.set_consent(db, c.id, "whatsapp", True, "manual")
    if mail:
        consent.set_consent(db, c.id, "email", True, "manual")
    db.flush()
    return c


def product(db, **fields):
    fields = {"name": "Test sandals", "category": "Shoes", "price": Decimal("1999"), "description": "Light summer sandals", "source": "manual", **fields}
    return campaigns.create_product(db, **{k: fields.get(k) for k in ("name", "category", "price", "description", "source", "external_id", "launch_project_id")})


def with_segments(monkeypatch, mapping):
    """Pretend the segmentation said these things (the real one needs hundreds of customers)."""
    monkeypatch.setattr(campaigns, "segment_by_customer", lambda db: dict(mapping))


GOOD = {
    "messages": {
        "champions": {"en": "Hi {{first_name}}, early access to {{product_name}} at {{price}}. {{last_purchase_line}}", "ur": "سلام {{first_name}}، {{product_name}} آپ کے لیے، قیمت {{price}}۔ {{last_purchase_line}}"},
        "other": {"en": "Hi {{first_name}}, new at {{store_name}}: {{product_name}} for {{price}}.", "ur": "سلام {{first_name}}، {{store_name}} میں نیا: {{product_name}}، قیمت {{price}}۔"},
    },
    "subject": {"en": "New: {{product_name}}", "ur": "نیا: {{product_name}}"},
}


class FakeModel:
    model = "fake-model"

    def __init__(self, answer):
        self.answer_text, self.calls = answer, 0

    def answer(self, instructions, turns):
        self.calls += 1
        assert "Do NOT invent" in instructions and "do not mention any discount" in instructions
        return self.answer_text if isinstance(self.answer_text, str) else json.dumps(self.answer_text)


def use_model(monkeypatch, answer):
    fake = FakeModel(answer)
    monkeypatch.setattr(launch_ai, "get_model", lambda s: fake)
    return fake


# --- products and drafts ---------------------------------------------------------------------------------------------------


def test_adding_a_product_makes_a_draft_campaign_and_nothing_is_sent(db_session):
    p, campaign = product(db_session)
    assert campaign.status == "draft" and campaign.product_id == p.id and campaign.name == "New: Test sandals"
    assert campaign.audience == {"categories": ["Shoes"], "segments": ["Champions"], "include_category_buyers": True}
    assert campaign.early_access_hours == 24 and campaign.messages is None and db_session.query(Message).count() == 0
    _, no_category = product(db_session, name="Test mystery box", category=None)
    assert no_category.audience["categories"] == []


def test_a_shopify_product_is_saved_once(db_session):
    first = product(db_session, name="Test lamp", source="shopify", external_id="9001")
    again = product(db_session, name="Test lamp", source="shopify", external_id="9001")
    assert first[0].id == again[0].id and first[1].id == again[1].id and db_session.query(CatalogProduct).count() == 1


# --- the audience ------------------------------------------------------------------------------------------------------------


def test_the_audience_is_category_buyers_plus_chosen_segments_and_only_people_who_agreed(db_session, monkeypatch):
    _, campaign = product(db_session)
    buyer = customer(db_session, name="Test Buyer")                                        # bought shoes
    champion = customer(db_session, name="Test Champion", category="Bags")                  # a champion who bought bags
    other = customer(db_session, name="Test Bags", category="Bags")                         # neither
    silent = customer(db_session, name="Test Silent", wa=False)                             # bought shoes but never agreed
    no_phone = customer(db_session, name="Test NoPhone", phone="+923001111111")
    no_phone.phone_normalised = None
    emailer = customer(db_session, name="Test Emailer", wa=False, mail=True)                # agreed to email only
    with_segments(monkeypatch, {champion.id: "champions", buyer.id: "loyal", other.id: "lost"})
    audience = campaigns.compute_audience(db_session, campaign)
    got = {m.customer.first_name: (m.segment, m.channel) for m in audience.members}
    assert got == {"Test Buyer": ("loyal", "whatsapp"), "Test Champion": ("champions", "whatsapp"), "Test Emailer": ("other", "email")}
    assert audience.candidates == 5 and audience.no_consent == 1 and audience.no_address == 1
    assert audience.by_segment() == {"loyal": 1, "champions": 1, "other": 1}
    assert silent.id and other.id


def test_the_seller_can_change_who_gets_it(db_session, monkeypatch):
    _, campaign = product(db_session)
    a, b = customer(db_session, name="Test A"), customer(db_session, name="Test B", category="Bags")
    with_segments(monkeypatch, {a.id: "loyal", b.id: "loyal"})
    campaign.audience = {"categories": ["Shoes"], "segments": [], "include_category_buyers": True}
    assert [m.customer.first_name for m in campaigns.compute_audience(db_session, campaign).members] == ["Test A"]
    campaign.audience = {"categories": [], "segments": ["Loyal Customers"], "include_category_buyers": False}
    assert {m.customer.first_name for m in campaigns.compute_audience(db_session, campaign).members} == {"Test A", "Test B"}


def test_a_customer_with_both_channels_gets_whatsapp(db_session, monkeypatch):
    _, campaign = product(db_session)
    both = customer(db_session, mail=True)
    with_segments(monkeypatch, {})
    assert campaigns.compute_audience(db_session, campaign).members[0].channel == "whatsapp" and both.id


# --- the AI draft -------------------------------------------------------------------------------------------------------------


def test_the_ai_writes_one_message_per_segment_in_both_languages_in_one_call_and_it_is_cached(db_session, monkeypatch):
    _, campaign = product(db_session)
    fake = use_model(monkeypatch, GOOD)
    product_row = db_session.get(CatalogProduct, campaign.product_id)
    result, cached, model = campaign_ai.generate(db_session, settings(), campaign, product_row, ["champions", "other"], "Test Boutique", force=False)
    assert cached is False and model == "fake-model" and fake.calls == 1
    assert set(result["messages"]) == {"champions", "other"} and result["messages"]["champions"]["ur"].startswith("سلام")
    again = campaign_ai.generate(db_session, settings(), campaign, product_row, ["champions", "other"], "Test Boutique", force=False)
    assert again[1] is True and fake.calls == 1
    campaign_ai.generate(db_session, settings(), campaign, product_row, ["champions"], "Test Boutique", force=False)       # different segments: a new question
    assert fake.calls == 2


def with_change(path_to, value):
    data = json.loads(json.dumps(GOOD))
    target = data
    for key in path_to[:-1]:
        target = target[key]
    target[path_to[-1]] = value
    return data


@pytest.mark.parametrize("answer,reason", [
    ("not json at all", "format"),
    ({"messages": "x", "subject": {}}, "format"),
    (with_change(["messages", "champions"], {"en": "Hi {{first_name}} only English here"}), "wrong length"),
    (with_change(["messages", "other"], None), "segment"),
    (with_change(["messages", "champions", "en"], "Hi {{frist_name}}, new {{product_name}} is here for you"), "not allowed"),
    (with_change(["messages", "champions", "en"], "Hi {{first_name}}, {{offer_text}} on {{product_name}} for you"), "offer you did not give"),
    (with_change(["messages", "champions", "en"], "Hi {{first_name}}, get 20% off {{product_name}} today only"), "claim or an offer"),
    (with_change(["messages", "champions", "en"], "Hi {{first_name}}, over 5000 sold, buy {{product_name}} now"), "claim or an offer"),
    (with_change(["messages", "champions", "ur"], "سلام {{first_name}}، {{product_name}} پر رعایت ہے آج"), "claim or an offer"),
    (with_change(["subject", "en"], "x"), "subject"),
])
def test_a_draft_that_breaks_the_rules_is_thrown_away(db_session, monkeypatch, answer, reason):
    _, campaign = product(db_session)
    use_model(monkeypatch, answer)
    product_row = db_session.get(CatalogProduct, campaign.product_id)
    with pytest.raises(ApiError) as caught:
        campaign_ai.generate(db_session, settings(), campaign, product_row, ["champions", "other"], None, force=False)
    assert caught.value.status_code == 502 and caught.value.code == "ai_bad_answer"
    assert db_session.query(launch_ai.AiCache).count() == 0                                   # a bad answer is never saved


def test_an_offer_is_allowed_only_when_the_seller_typed_one(db_session, monkeypatch):
    _, campaign = product(db_session)
    use_model(monkeypatch, with_change(["messages", "champions", "en"], "Hi {{first_name}}, {{offer_text}} on {{product_name}} for you"))
    campaign.offer_text = "Free delivery this week"
    product_row = db_session.get(CatalogProduct, campaign.product_id)
    result = campaign_ai.generate(db_session, settings(), campaign, product_row, ["champions", "other"], None, force=False)[0]
    assert "{{offer_text}}" in result["messages"]["champions"]["en"]
    assert campaigns.invents_an_offer("Big sale today", None) and not campaigns.invents_an_offer("Big sale today", "Sale on shoes")
    assert not campaigns.invents_an_offer("Hello {{first_name}}, a new product is here", None)


def test_a_price_may_only_be_used_when_the_product_has_one(db_session, monkeypatch):
    _, campaign = product(db_session, price=None)
    use_model(monkeypatch, GOOD)
    product_row = db_session.get(CatalogProduct, campaign.product_id)
    with pytest.raises(ApiError) as caught:
        campaign_ai.generate(db_session, settings(), campaign, product_row, ["champions", "other"], None, force=False)
    assert "price" in caught.value.message


# --- the preview ----------------------------------------------------------------------------------------------------------------


def written(campaign):
    campaign.messages = json.loads(json.dumps(GOOD))
    campaign.ai_draft = True


def test_the_preview_shows_five_real_samples_with_one_per_segment_first(db_session, monkeypatch):
    p, campaign = product(db_session)
    written(campaign)
    people = [customer(db_session, name=f"Test Person{i}") for i in range(8)]
    with_segments(monkeypatch, {people[0].id: "other", people[1].id: "champions", people[2].id: "champions"})
    samples, audience = campaigns.preview(db_session, campaign)
    assert len(samples) == 5 and audience.members and [s.segment for s in samples][:2] == ["other", "champions"]
    champion = next(s for s in samples if s.segment == "champions")
    assert champion.customer_name.startswith("Test Person") and "Test sandals" in champion.text and "Rs 1,999" in champion.text and champion.error is None
    assert "Reply STOP" in champion.text                                                          # WhatsApp marketing always carries the stop line
    assert "Last time you bought Test shoes." in champion.text


def test_a_segment_without_a_message_is_shown_as_missing_not_hidden(db_session, monkeypatch):
    _, campaign = product(db_session)
    written(campaign)
    campaign.messages["messages"].pop("other")
    c = customer(db_session)
    with_segments(monkeypatch, {c.id: "lost"})
    sample = campaigns.preview(db_session, campaign)[0][0]
    assert sample.text is None and "No message written" in sample.error


def test_the_customers_language_picks_the_urdu_or_english_text(db_session, monkeypatch):
    _, campaign = product(db_session)
    written(campaign)
    urdu, english = customer(db_session, name="Test Urdu", language="ur"), customer(db_session, name="Test English")
    with_segments(monkeypatch, {urdu.id: "champions", english.id: "champions"})
    by_name = {s.customer_name: s for s in campaigns.preview(db_session, campaign)[0]}
    assert by_name["Test Urdu"].language == "ur" and "آپ کے لیے" in by_name["Test Urdu"].text and by_name["Test English"].language == "en"


# --- approving and sending ------------------------------------------------------------------------------------------------------------


def ready(db_session, monkeypatch, n=6, champions=2):
    p, campaign = product(db_session)
    written(campaign)
    people = [customer(db_session, name=f"Test Person{i}") for i in range(n)]
    with_segments(monkeypatch, {c.id: ("champions" if i < champions else "other") for i, c in enumerate(people)})
    return campaign, people


def test_approving_makes_approved_templates_and_schedules_champions_first(db_session, monkeypatch):
    campaign, people = ready(db_session, monkeypatch)
    assert campaigns.approve(db_session, campaign, NOW) == {"recipients": 6, "early": 2}
    assert campaign.status == "approved" and campaign.approved_at == NOW and campaign.ai_draft is False
    recipients = {r.customer_id: r for r in db_session.query(CampaignRecipient).filter_by(campaign_id=campaign.id)}
    assert sorted(r.stage for r in recipients.values()) == ["early"] * 2 + ["regular"] * 4
    assert recipients[people[0].id].scheduled_for == NOW and recipients[people[3].id].scheduled_for == NOW + timedelta(hours=24)
    wa = db_session.query(MessageTemplate).filter_by(name=f"campaign_{campaign.id}_champions_en").one()
    assert wa.approved_by_seller and wa.category == "marketing" and wa.event == f"campaign_{campaign.id}" and "Reply STOP to stop messages." in wa.body
    ur = db_session.query(MessageTemplate).filter_by(name=f"campaign_{campaign.id}_champions_ur").one()
    assert "STOP" in ur.body
    mail = db_session.query(MessageTemplate).filter_by(name=f"campaign_{campaign.id}_champions_en_email").one()
    assert mail.subject == "New: {{product_name}}" and "STOP" not in mail.body


def test_without_champions_everyone_goes_at_once(db_session, monkeypatch):
    campaign, _ = ready(db_session, monkeypatch, n=3, champions=0)
    assert campaigns.approve(db_session, campaign, NOW)["early"] == 0
    assert {r.scheduled_for for r in db_session.query(CampaignRecipient)} == {NOW}


def test_zero_early_access_hours_sends_to_everyone_at_once(db_session, monkeypatch):
    campaign, _ = ready(db_session, monkeypatch)
    campaign.early_access_hours = 0
    campaigns.approve(db_session, campaign, NOW)
    assert {r.scheduled_for for r in db_session.query(CampaignRecipient)} == {NOW}


def test_approval_is_refused_for_an_empty_audience_missing_text_or_a_second_time(db_session, monkeypatch):
    _, empty = product(db_session)
    written(empty)
    with_segments(monkeypatch, {})
    with pytest.raises(ApiError) as caught:
        campaigns.approve(db_session, empty, NOW)
    assert caught.value.code == "empty_audience"

    campaign, people = ready(db_session, monkeypatch)
    campaign.messages["messages"]["other"]["ur"] = ""
    with pytest.raises(ApiError) as caught:
        campaigns.approve(db_session, campaign, NOW)
    assert caught.value.code == "messages_missing" and db_session.query(CampaignRecipient).count() == 0 and campaign.status == "draft"
    campaign.messages["messages"]["other"]["ur"] = "سلام {{first_name}}"
    campaigns.approve(db_session, campaign, NOW)
    with pytest.raises(ApiError) as caught:
        campaigns.approve(db_session, campaign, NOW)
    assert caught.value.code == "not_a_draft"


def test_sending_goes_in_batches_champions_first_then_the_rest_after_the_early_hours(db_session, monkeypatch):
    campaign, people = ready(db_session, monkeypatch)
    get_row(db_session).campaign_batch_size = 2
    campaigns.approve(db_session, campaign, NOW)
    first = campaigns.send_due_batches(db_session, settings(), NOW)
    assert first == {"campaigns": 1, "sent": 2, "skipped": 0} and campaign.status == "sending"
    sent_to = {db_session.get(Customer, r.customer_id).first_name for r in db_session.query(CampaignRecipient).filter_by(status="sent")}
    assert sent_to == {"Test Person0", "Test Person1"}                                                  # the champions
    assert campaigns.send_due_batches(db_session, settings(), NOW + timedelta(hours=23))["sent"] == 0       # the rest are not due yet
    assert campaigns.send_due_batches(db_session, settings(), NOW + timedelta(hours=24))["sent"] == 2       # a batch of 2
    assert campaigns.send_due_batches(db_session, settings(), NOW + timedelta(hours=24))["sent"] == 2
    assert campaign.status == "completed" and campaign.completed_at is not None
    assert campaigns.send_due_batches(db_session, settings(), NOW + timedelta(hours=30)) == {"campaigns": 0, "sent": 0, "skipped": 0}
    messages = db_session.query(Message).filter_by(campaign_id=campaign.id).all()
    assert len(messages) == 6 and all(m.category == "marketing" and m.status == "sent" for m in messages)
    assert all("Reply STOP" in m.rendered_text for m in messages)


def test_running_the_same_pass_twice_never_sends_twice(db_session, monkeypatch):
    campaign, _ = ready(db_session, monkeypatch, n=3, champions=0)
    campaigns.approve(db_session, campaign, NOW)
    campaigns.send_due_batches(db_session, settings(), NOW)
    campaigns.send_due_batches(db_session, settings(), NOW)
    assert db_session.query(Message).filter_by(campaign_id=campaign.id).count() == 3


def test_someone_who_stops_after_approval_is_skipped(db_session, monkeypatch):
    campaign, people = ready(db_session, monkeypatch, n=3, champions=0)
    campaigns.approve(db_session, campaign, NOW)
    consent.set_consent(db_session, people[0].id, "whatsapp", False, "whatsapp_stop")
    counts = campaigns.send_due_batches(db_session, settings(), NOW)
    assert counts["sent"] == 2 and counts["skipped"] == 1
    skipped = db_session.query(CampaignRecipient).filter_by(status="skipped").one()
    assert skipped.customer_id == people[0].id and skipped.reason == "no_consent"


def test_the_weekly_cap_still_applies_to_campaign_messages(db_session, monkeypatch):
    campaign, people = ready(db_session, monkeypatch, n=2, champions=0)
    get_row(db_session).weekly_marketing_cap = 1
    campaigns.approve(db_session, campaign, NOW)
    db_session.add(Message(customer_id=people[0].id, channel="whatsapp", category="marketing", rendered_text="earlier promo", status="sent", idempotency_key="test-earlier",
                           queued_at=NOW - timedelta(days=2), sent_at=NOW - timedelta(days=2)))
    db_session.flush()
    counts = campaigns.send_due_batches(db_session, settings(), NOW)
    assert counts["sent"] == 1 and db_session.query(CampaignRecipient).filter_by(status="skipped").one().reason == "weekly_cap"


def test_a_customer_who_only_agreed_to_email_gets_an_email(db_session, monkeypatch):
    campaign, _ = ready(db_session, monkeypatch, n=1, champions=0)
    emailer = customer(db_session, name="Test Emailer", wa=False, mail=True)
    with_segments(monkeypatch, {emailer.id: "other"})
    campaigns.approve(db_session, campaign, NOW)
    campaigns.send_due_batches(db_session, settings(), NOW)
    message = db_session.query(Message).filter_by(customer_id=emailer.id).one()
    assert message.channel == "email" and message.subject == "New: Test sandals" and "Reply STOP" not in message.rendered_text


def test_cancelling_stops_the_ones_not_yet_messaged(db_session, monkeypatch):
    campaign, _ = ready(db_session, monkeypatch)
    campaigns.approve(db_session, campaign, NOW)
    campaigns.send_due_batches(db_session, settings(), NOW)
    assert campaigns.cancel(db_session, campaign) == 4 and campaign.status == "cancelled"
    assert campaigns.send_due_batches(db_session, settings(), NOW + timedelta(days=2))["sent"] == 0
    assert {r.reason for r in db_session.query(CampaignRecipient).filter_by(status="skipped")} == {"campaign_cancelled"}


# --- HTTP ------------------------------------------------------------------------------------------------------------------------------


def test_the_whole_flow_over_http(db_client, db_session, monkeypatch):
    app.dependency_overrides[get_settings] = lambda: settings()
    a, b = customer(db_session, name="Test A"), customer(db_session, name="Test B")
    with_segments(monkeypatch, {a.id: "champions"})
    created = db_client.post("/api/v1/messaging/products", json={"name": "Test sandals", "category": "Shoes", "price": 1999, "description": "Light summer sandals"})
    assert created.status_code == 201
    cid = created.json()["campaignId"]
    detail = db_client.get(f"/api/v1/messaging/campaigns/{cid}").json()
    assert detail["status"] == "draft" and detail["audience"]["segments"] == ["Champions"] and detail["messages"] is None and detail["counts"]["total"] == 0

    assert db_client.post(f"/api/v1/messaging/campaigns/{cid}/approve").status_code == 422                   # no wording yet
    fake = use_model(monkeypatch, GOOD)
    draft = db_client.post(f"/api/v1/messaging/campaigns/{cid}/generate", json={}).json()
    assert draft["label"] == "AI draft" and draft["cached"] is False and draft["campaign"]["aiDraft"] is True and fake.calls == 1
    assert db_client.post(f"/api/v1/messaging/campaigns/{cid}/generate", json={}).json()["cached"] is True and fake.calls == 1

    edited = db_client.put(f"/api/v1/messaging/campaigns/{cid}/messages", json={
        "messages": {"champions": {"en": "My own text for {{first_name}}: {{product_name}}", "ur": "میرا متن {{first_name}}"}, "other": {"en": "Hello {{first_name}}", "ur": "سلام {{first_name}}"}},
        "subject": {"en": "New: {{product_name}}", "ur": "نیا"},
    }).json()
    assert edited["aiDraft"] is False and edited["messages"]["messages"]["champions"]["en"].startswith("My own text")
    assert db_client.put(f"/api/v1/messaging/campaigns/{cid}/messages", json={"messages": {"champions": {"en": "Hi {{oops}}"}}, "subject": {"en": "x", "ur": "y"}}).status_code == 422
    assert db_client.put(f"/api/v1/messaging/campaigns/{cid}/messages", json={"messages": {"nonsense": {"en": "x"}}, "subject": {"en": "x", "ur": "y"}}).status_code == 422

    preview = db_client.get(f"/api/v1/messaging/campaigns/{cid}/preview").json()
    assert preview["label"].startswith("Real customers") and preview["audience"]["eligible"] == 2 and preview["audience"]["noConsent"] == 0
    assert any("My own text for Test A" in (s["text"] or "") for s in preview["samples"])

    changed = db_client.patch(f"/api/v1/messaging/campaigns/{cid}", json={"offerText": "Free delivery", "earlyAccessHours": 12}).json()
    assert changed["offerText"] == "Free delivery" and changed["earlyAccessHours"] == 12
    approved = db_client.post(f"/api/v1/messaging/campaigns/{cid}/approve").json()
    assert approved == {"recipients": 2, "early": 1}
    assert db_client.patch(f"/api/v1/messaging/campaigns/{cid}", json={"name": "Too late"}).status_code == 409
    assert db_client.post(f"/api/v1/messaging/campaigns/{cid}/generate", json={}).status_code == 409
    assert db_client.delete(f"/api/v1/messaging/campaigns/{cid}").status_code == 409
    recipients = db_client.get(f"/api/v1/messaging/campaigns/{cid}/recipients").json()
    assert [r["stage"] for r in recipients] == ["early", "regular"] and {r["status"] for r in recipients} == {"pending"}
    assert db_client.get(f"/api/v1/messaging/campaigns/{cid}/recipients?show=sent").json() == []
    assert db_client.post(f"/api/v1/messaging/campaigns/{cid}/cancel").json() == {"stopped": 2}
    assert db_client.delete(f"/api/v1/messaging/campaigns/{cid}").status_code == 204
    assert db_client.get(f"/api/v1/messaging/campaigns/{cid}").status_code == 404


def test_generating_for_an_empty_audience_and_the_ai_limit(db_client, db_session, monkeypatch):
    import uuid
    from types import SimpleNamespace

    from app.api.deps import require_user
    from app.services.rate_limit import reset_rate_limits

    app.dependency_overrides[get_settings] = lambda: settings()
    with_segments(monkeypatch, {})
    cid = db_client.post("/api/v1/messaging/products", json={"name": "Test lamp", "category": "Lamps"}).json()["campaignId"]
    assert db_client.post(f"/api/v1/messaging/campaigns/{cid}/generate", json={}).json()["error"]["code"] == "empty_audience"

    reset_rate_limits()
    import app.api.v1.campaigns as api

    monkeypatch.setattr(api, "AI_CALLS_PER_WINDOW", 1)
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=uuid.uuid4(), email="t@example.com", name="T")
    same = SimpleNamespace(id=uuid.uuid4(), email="t@example.com", name="T")
    app.dependency_overrides[require_user] = lambda: same
    c = customer(db_session)
    with_segments(monkeypatch, {c.id: "champions"})
    use_model(monkeypatch, GOOD)
    cid2 = db_client.post("/api/v1/messaging/products", json={"name": "Test sandals", "category": "Shoes", "price": 1999}).json()["campaignId"]
    assert db_client.post(f"/api/v1/messaging/campaigns/{cid2}/generate", json={"force": True}).status_code == 200
    assert db_client.post(f"/api/v1/messaging/campaigns/{cid2}/generate", json={"force": True}).status_code == 429
    reset_rate_limits()


def test_a_product_from_launch_studio_makes_a_draft_once(db_client, db_session):
    project = LaunchProject(product_name="Test neck fan", category="Gadgets", notes="USB rechargeable fan")
    db_session.add(project)
    db_session.flush()
    first = db_client.post(f"/api/v1/messaging/products/from-launch/{project.id}")
    assert first.status_code == 201 and first.json()["source"] == "launch_studio" and first.json()["description"] == "USB rechargeable fan"
    again = db_client.post(f"/api/v1/messaging/products/from-launch/{project.id}")
    assert again.json()["id"] == first.json()["id"] and db_session.query(CatalogProduct).count() == 1
    assert db_client.post("/api/v1/messaging/products/from-launch/999999").status_code == 404
    assert [p["name"] for p in db_client.get("/api/v1/messaging/products").json()] == ["Test neck fan"]


def test_a_shopify_new_product_webhook_makes_a_draft_campaign(db_session):
    payload = {"id": 777, "title": "Test lamp", "product_type": "Lamps", "body_html": "<p>A <b>warm</b> light</p>", "variants": [{"price": "999.00"}]}
    result = shopify_hooks.handle(db_session, settings(), "products/create", payload)
    assert result["product"] == "Test lamp" and result["status"] == "draft"
    p = db_session.query(CatalogProduct).one()
    assert (p.category, p.price, p.description, p.source, p.external_id) == ("Lamps", Decimal("999.00"), "A warm light", "shopify", "777")
    assert shopify_hooks.handle(db_session, settings(), "products/create", payload)["campaign"] == result["campaign"]
    assert db_session.query(Campaign).count() == 1
    assert "ignored" in shopify_hooks.handle(db_session, settings(), "products/create", {"id": 1})


def test_validation_of_products_and_campaign_edits(db_client):
    assert db_client.post("/api/v1/messaging/products", json={"name": "x"}).status_code == 422
    assert db_client.post("/api/v1/messaging/products", json={"name": "Test ok", "price": -5}).status_code == 422
    cid = db_client.post("/api/v1/messaging/products", json={"name": "Test ok"}).json()["campaignId"]
    assert db_client.patch(f"/api/v1/messaging/campaigns/{cid}", json={"earlyAccessHours": 999}).status_code == 422
    assert db_client.patch(f"/api/v1/messaging/campaigns/{cid}", json={"audience": {"segments": ["Nobody"]}}).status_code == 422
    assert db_client.get("/api/v1/messaging/campaigns/999999").status_code == 404
