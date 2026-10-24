"""Auto Messenger part 1: template rendering, quiet hours, weekly cap, consent, idempotency, retries, STOP and the
webhook signature. All customers, numbers, templates and payloads are MADE UP for the tests (marked TEST)."""

import hashlib
import hmac
import json
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import Customer, IncomingMessage, Message, MessageTemplate
from app.services.messaging import adapters, consent, policy, service, tokens, webhook
from app.services.messaging.adapters import Outbound, SendResult
from app.services.messaging.render import MissingVariable, check_template_text, meta_style, render, variables_in
from app.services.messaging.settings_store import get_row
from app.services.messaging.text_rules import is_stop, normalise, yes_or_no

PKT = timezone(timedelta(hours=5))


def local(hour, minute=0, day=10):
    """A moment in Pakistan time (UTC+5), as UTC."""
    return datetime(2026, 3, day, hour, minute, tzinfo=PKT).astimezone(timezone.utc)


def make_settings(**changes) -> Settings:
    return Settings(_env_file=None, messaging_dry_run=changes.pop("messaging_dry_run", True), **changes)


# --- render ---------------------------------------------------------------------------------------------


def test_variables_are_found_in_order_without_repeats():
    assert variables_in("Hi {{first_name}}, {{ order_number }} and {{first_name}} again") == ["first_name", "order_number"]


def test_render_fills_values_and_tidies_an_empty_optional_part():
    text = "Hello {{first_name}}!\nOrder {{order_number}}. {{cod_note}}\n{{tracking_line}}\nThanks"
    assert render(text, {"first_name": "Test Ali", "order_number": "T-1", "cod_note": "Keep Rs 500 ready.", "tracking_line": None}) == "Hello Test Ali!\nOrder T-1. Keep Rs 500 ready.\n\nThanks"
    assert render("A {{cod_note}} B", {"cod_note": ""}) == "A B"


def test_a_missing_required_variable_stops_the_message():
    with pytest.raises(MissingVariable) as caught:
        render("Hi {{first_name}}", {"first_name": "  "})
    assert caught.value.name == "first_name"


def test_unknown_variables_are_refused_when_the_template_is_saved():
    assert check_template_text("Hi {{first_name}}") == ["first_name"]
    with pytest.raises(ApiError) as caught:
        check_template_text("Hi {{frist_name}}")
    assert caught.value.code == "unknown_variable"
    with pytest.raises(ApiError):
        check_template_text("   ")
    with pytest.raises(ApiError):
        check_template_text("x" * 2000)
    with pytest.raises(ApiError):
        check_template_text("fine", subject="Hi {{nope}}")


def test_meta_style_numbers_the_variables_in_order():
    body, order = meta_style("Hi {{first_name}}, order {{order_number}} for {{first_name}}")
    assert body == "Hi {{1}}, order {{2}} for {{1}}" and order == ["first_name", "order_number"]


# --- quiet hours and the weekly cap ------------------------------------------------------------------------


@pytest.mark.parametrize("hour,minute,allowed", [(9, 59, False), (10, 0, True), (15, 0, True), (20, 59, True), (21, 0, False), (23, 30, False), (2, 0, False)])
def test_quiet_hours_boundaries(hour, minute, allowed):
    moment = datetime(2026, 3, 10, hour, minute, tzinfo=PKT)
    assert policy.is_allowed(moment, time(21, 0), time(10, 0)) is allowed


def test_out_for_delivery_may_go_out_from_8_am():
    moment = datetime(2026, 3, 10, 8, 30, tzinfo=PKT)
    assert policy.is_allowed(moment, time(21, 0), time(10, 0), "order_out_for_delivery")
    assert not policy.is_allowed(moment, time(21, 0), time(10, 0), "order_dispatched")
    assert not policy.is_allowed(datetime(2026, 3, 10, 7, 59, tzinfo=PKT), time(21, 0), time(10, 0), "order_out_for_delivery")
    assert not policy.is_allowed(datetime(2026, 3, 10, 21, 0, tzinfo=PKT), time(21, 0), time(10, 0), "order_out_for_delivery")


def test_next_allowed_is_now_or_the_next_opening():
    assert policy.next_allowed(local(12), "Asia/Karachi", time(21, 0), time(10, 0)) == local(12)
    assert policy.next_allowed(local(22), "Asia/Karachi", time(21, 0), time(10, 0)) == local(10, day=11)       # after 21:00: tomorrow 10:00
    assert policy.next_allowed(local(3), "Asia/Karachi", time(21, 0), time(10, 0)) == local(10)               # before 10:00: today 10:00
    assert policy.next_allowed(local(3), "Asia/Karachi", time(21, 0), time(10, 0), "order_out_for_delivery") == local(8)


def test_the_weekly_cap():
    assert policy.cap_allows(0, 2) and policy.cap_allows(1, 2)
    assert not policy.cap_allows(2, 2) and not policy.cap_allows(5, 2)
    assert not policy.cap_allows(0, 0)


# --- STOP, YES, NO ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["STOP", "  stop!! ", "Stop", "unsubscribe", "Band karo", "band kro", "BAND KAR DO", "بند کرو", "بند کریں", "stop messages", "stop please", "mat bhejo", "رک"[:0] or "روک دو"])
def test_stop_requests_are_recognised(text):
    assert is_stop(text)


@pytest.mark.parametrize("text", ["", None, "Please do not stop the delivery of my order today", "hello", "thanks", "ok", "when will it arrive", "stoppage"])
def test_ordinary_messages_are_not_stop_requests(text):
    assert not is_stop(text)


def test_yes_and_no_answers():
    assert yes_or_no("YES") == "yes" and yes_or_no("haan") == "yes" and yes_or_no("جی ہاں") == "yes" and yes_or_no("Ok!") == "yes"
    assert yes_or_no("No") == "no" and yes_or_no("nahi") == "no" and yes_or_no("نہیں") == "no"
    assert yes_or_no("maybe later") is None and yes_or_no(None) is None
    assert normalise("  Hello,   WORLD! ") == "hello world"


# --- unsubscribe tokens ----------------------------------------------------------------------------------------


def test_unsubscribe_tokens_cannot_be_forged():
    settings = make_settings(messaging_secret="test-secret-for-the-tests", public_api_url="https://api.test.invalid/")
    token = tokens.make_unsubscribe_token(settings, 42, "email")
    assert tokens.read_unsubscribe_token(settings, token) == (42, "email")
    assert tokens.unsubscribe_link(settings, 42) == f"https://api.test.invalid/api/v1/unsubscribe?token={token}"
    other = make_settings(messaging_secret="another-secret")
    assert tokens.read_unsubscribe_token(other, token) is None                          # a different secret
    forged = tokens.make_unsubscribe_token(settings, 43, "email")
    assert tokens.read_unsubscribe_token(settings, forged) == (43, "email")             # genuine for 43 only
    for bad in ("", "garbage", token[:-3] + "AAA", "a" * 200):
        assert tokens.read_unsubscribe_token(settings, bad) is None
    assert tokens.make_unsubscribe_token(make_settings(), 42, "email") is None         # no secret, no link
    assert tokens.read_unsubscribe_token(make_settings(), token) is None


# --- helpers for the database tests ------------------------------------------------------------------------------


_n = [0]


def make_customer(db, *, phone="+923001234567", email="test.customer@testcustomer.test", name="Test Ali"):
    _n[0] += 1
    customer = Customer(external_id=f"TEST-C{_n[0]}", first_name=name, phone=phone, phone_normalised=phone, email=email, country="Pakistan")
    db.add(customer)
    db.flush()
    return customer


def make_template(db, *, channel="whatsapp", category="utility", body="Hello {{first_name}}, TEST message from {{store_name}}.", approved=True, **fields):
    _n[0] += 1
    template = MessageTemplate(
        name=f"test_{_n[0]}", channel=channel, category=category, language=fields.pop("language", "en"), body=body,
        subject="TEST subject for {{first_name}}" if channel == "email" else None, approved_by_seller=approved, **fields,
    )
    db.add(template)
    db.flush()
    return template


def opt_in(db, customer, channel="whatsapp"):
    consent.set_consent(db, customer.id, channel, True, "manual")


def vars_for(db, customer, language="en"):
    return service.customer_variables(customer, get_row(db), language)


def send(db, customer, template, *, event_key="e1", now=None, settings=None, channel=None, **kw):
    return service.send_message(
        db, settings or make_settings(), customer, channel or template.channel, template, vars_for(db, customer, template.language),
        event_key=event_key, now=now or local(12), **kw,
    )


# --- consent ---------------------------------------------------------------------------------------------------


def test_nobody_is_messaged_without_consent(db_session):
    customer, template = make_customer(db_session), make_template(db_session)
    message = send(db_session, customer, template)
    assert (message.status, message.error) == ("skipped", "no_consent")


def test_consent_changes_are_recorded_and_a_repeat_adds_nothing(db_session):
    customer = make_customer(db_session)
    consent.set_consent(db_session, customer.id, "whatsapp", True, "manual", today=date(2026, 3, 1))
    consent.set_consent(db_session, customer.id, "whatsapp", True, "import")                      # already in: no change, no event
    consent.set_consent(db_session, customer.id, "whatsapp", False, "whatsapp_stop", note="Customer replied STOP")
    row = consent.get_consent(db_session, customer.id, "whatsapp")
    assert row.opted_in is False and row.source == "whatsapp_stop"
    events = [(e.action, e.source) for e in db_session.query(consent.ConsentEvent).filter_by(customer_id=customer.id).order_by("id")]
    assert events == [("opt_in", "manual"), ("opt_out", "whatsapp_stop")]
    assert consent.consent_state(db_session, customer.id, "whatsapp") == "opted_out"
    assert consent.consent_state(db_session, customer.id, "email") == "none"
    with pytest.raises(ApiError):
        consent.set_consent(db_session, customer.id, "sms", True, "manual")


def test_an_opted_out_customer_is_never_messaged(db_session):
    customer, template = make_customer(db_session), make_template(db_session)
    opt_in(db_session, customer)
    consent.set_consent(db_session, customer.id, "whatsapp", False, "manual")
    assert send(db_session, customer, template).error == "opted_out"


def test_consent_on_one_channel_does_not_allow_the_other(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer, "email")
    assert send(db_session, customer, make_template(db_session, channel="whatsapp")).error == "no_consent"
    assert send(db_session, customer, make_template(db_session, channel="email"), event_key="e2").status == "sent"


# --- the order of the checks ----------------------------------------------------------------------------------------


def test_an_unapproved_template_is_never_sent(db_session):
    customer, template = make_customer(db_session), make_template(db_session, approved=False)
    opt_in(db_session, customer)
    assert send(db_session, customer, template).error == "template_not_approved"


def test_missing_addresses_are_recorded(db_session):
    no_phone, no_email = make_customer(db_session, phone=None), make_customer(db_session, email=None)
    opt_in(db_session, no_phone)
    opt_in(db_session, no_email, "email")
    assert send(db_session, no_phone, make_template(db_session)).error == "no_phone"
    assert send(db_session, no_email, make_template(db_session, channel="email")).error == "no_email"
    placeholder = make_customer(db_session, email="pub-1@example.com", phone="+923001111111")                             # the public dataset's placeholder
    opt_in(db_session, placeholder, "email")
    assert send(db_session, placeholder, make_template(db_session, channel="email")).error == "no_email"


def test_a_missing_variable_is_recorded_and_nothing_is_invented(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    template = make_template(db_session, body="Hi {{first_name}}, your order {{order_number}} is ready.")
    message = send(db_session, customer, template)
    assert message.status == "skipped" and message.error == "missing_variable:order_number"


def test_a_ready_message_is_rendered_and_sent_in_dry_run(db_session):
    customer, template = make_customer(db_session), make_template(db_session)
    opt_in(db_session, customer)
    message = send(db_session, customer, template, order_id=None)
    assert message.status == "sent" and message.dry_run is True and message.provider_message_id.startswith("dryrun-")
    assert message.rendered_text == "Hello Test Ali, TEST message from our shop." and message.attempts == 1 and message.sent_at is not None


def test_the_shop_name_comes_from_the_settings(db_session):
    customer, template = make_customer(db_session), make_template(db_session)
    opt_in(db_session, customer)
    get_row(db_session).store_name = "Test Boutique"
    assert "Test Boutique" in send(db_session, customer, template).rendered_text


# --- idempotency ------------------------------------------------------------------------------------------------------


def test_the_same_event_is_never_sent_twice(db_session):
    customer, template = make_customer(db_session), make_template(db_session)
    opt_in(db_session, customer)
    first = send(db_session, customer, template, event_key="order-1:dispatched")
    again = send(db_session, customer, template, event_key="order-1:dispatched")
    other = send(db_session, customer, template, event_key="order-1:delivered")
    assert again.id == first.id and other.id != first.id
    assert db_session.query(Message).filter_by(customer_id=customer.id).count() == 2


# --- weekly cap -------------------------------------------------------------------------------------------------------


def test_marketing_is_capped_per_rolling_week_but_order_updates_are_not(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    promo = make_template(db_session, category="marketing", body="TEST offer for {{first_name}}. Reply STOP to stop.")
    update = make_template(db_session, category="utility")
    results = [send(db_session, customer, promo, event_key=f"promo-{i}", now=local(12, day=10 + i)).status for i in range(3)]   # days 10, 11, 12
    assert results == ["sent", "sent", "skipped"]
    assert db_session.query(Message).filter_by(customer_id=customer.id, error="weekly_cap").count() == 1
    assert send(db_session, customer, update, event_key="u1", now=local(12, day=12)).status == "sent"        # not capped
    assert send(db_session, customer, promo, event_key="promo-later", now=local(12, day=18)).status == "sent"    # the first one is now over 7 days old


def test_the_cap_can_be_changed_in_the_settings(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    promo = make_template(db_session, category="marketing")
    get_row(db_session).weekly_marketing_cap = 1
    assert send(db_session, customer, promo, event_key="a").status == "sent"
    assert send(db_session, customer, promo, event_key="b").error == "weekly_cap"
    get_row(db_session).weekly_marketing_cap = 0
    assert send(db_session, customer, promo, event_key="c").error == "weekly_cap"


# --- quiet hours and the queue ---------------------------------------------------------------------------------------------


def test_a_message_in_quiet_hours_waits_and_is_sent_when_the_window_opens(db_session):
    customer, template = make_customer(db_session), make_template(db_session)
    opt_in(db_session, customer)
    held = send(db_session, customer, template, now=local(22, 30))
    assert held.status == "queued" and held.next_attempt_at == local(10, day=11) and held.sent_at is None
    assert service.process_queue(db_session, make_settings(), now=local(23)) == {"processed": 0, "sent": 0, "requeued": 0, "failed": 0, "skipped": 0}
    counts = service.process_queue(db_session, make_settings(), now=local(10, 1, day=11))
    assert counts["sent"] == 1 and held.status == "sent"


def test_opting_out_while_a_message_waits_cancels_it(db_session):
    customer, template = make_customer(db_session), make_template(db_session)
    opt_in(db_session, customer)
    held = send(db_session, customer, template, now=local(23))
    consent.set_consent(db_session, customer.id, "whatsapp", False, "whatsapp_stop")
    assert (held.status, held.error) == ("skipped", "opted_out")
    assert service.process_queue(db_session, make_settings(), now=local(10, 1, day=11))["processed"] == 0


def test_out_for_delivery_is_not_held_after_8_am(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    template = make_template(db_session, event="order_out_for_delivery")
    assert send(db_session, customer, template, now=local(8, 30)).status == "sent"
    other = make_template(db_session, event="order_dispatched")
    assert send(db_session, customer, other, event_key="e2", now=local(8, 30)).status == "queued"


# --- retries ---------------------------------------------------------------------------------------------------------------------


class ScriptedAdapter:
    def __init__(self, results):
        self.results, self.calls = list(results), []

    def send(self, out: Outbound) -> SendResult:
        self.calls.append(out)
        return self.results.pop(0)


def use_adapter(monkeypatch, adapter):
    monkeypatch.setattr(service, "adapter_for", lambda channel, settings, dry: adapter)


def test_a_temporary_failure_is_retried_with_a_wait_and_then_succeeds(db_session, monkeypatch):
    customer, template = make_customer(db_session), make_template(db_session)
    opt_in(db_session, customer)
    adapter = ScriptedAdapter([SendResult(False, error="whatsapp_network", transient=True)] * 2 + [SendResult(True, "wamid.TEST1")])
    use_adapter(monkeypatch, adapter)
    message = send(db_session, customer, template, now=local(12))
    assert (message.status, message.attempts, message.error) == ("queued", 1, "whatsapp_network") and message.next_attempt_at == local(12) + timedelta(minutes=5)
    service.process_queue(db_session, make_settings(), now=local(12, 6))
    assert (message.status, message.attempts) == ("queued", 2) and message.next_attempt_at == local(12, 6) + timedelta(minutes=30)
    service.process_queue(db_session, make_settings(), now=local(12, 40))
    assert (message.status, message.attempts, message.provider_message_id, message.error) == ("sent", 3, "wamid.TEST1", None)


def test_retries_stop_after_three_tries(db_session, monkeypatch):
    customer, template = make_customer(db_session), make_template(db_session)
    opt_in(db_session, customer)
    adapter = ScriptedAdapter([SendResult(False, error="whatsapp_503", transient=True)] * 3)
    use_adapter(monkeypatch, adapter)
    message = send(db_session, customer, template, now=local(12))
    service.process_queue(db_session, make_settings(), now=local(12, 6))
    service.process_queue(db_session, make_settings(), now=local(12, 40))
    assert (message.status, message.attempts, message.failed_at is not None) == ("failed", 3, True)
    assert len(adapter.calls) == 3 and service.process_queue(db_session, make_settings(), now=local(18))["processed"] == 0


def test_a_permanent_failure_is_not_retried(db_session, monkeypatch):
    customer, template = make_customer(db_session), make_template(db_session)
    opt_in(db_session, customer)
    adapter = ScriptedAdapter([SendResult(False, error="whatsapp_131026", transient=False)])
    use_adapter(monkeypatch, adapter)
    message = send(db_session, customer, template)
    assert (message.status, message.error, message.attempts) == ("failed", "whatsapp_131026", 1) and message.next_attempt_at is None


# --- real sending rules (dry run off) ------------------------------------------------------------------------------------------------


def test_whatsapp_needs_a_template_approved_by_meta_unless_the_customer_wrote_first(db_session, monkeypatch):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    live = make_settings(messaging_dry_run=False)
    get_row(db_session).dry_run = False
    adapter = ScriptedAdapter([SendResult(True, "wamid.A"), SendResult(True, "wamid.B")])
    use_adapter(monkeypatch, adapter)

    plain = make_template(db_session)
    assert send(db_session, customer, plain, settings=live, event_key="a").error == "meta_template_not_approved"

    approved = make_template(db_session, body="Hi {{first_name}}, TEST order {{order_number}}.", meta_template_name="test_order_update", meta_approval_status="approved")
    values = service.customer_variables(customer, get_row(db_session), "en", {"order_number": "T-9"})
    sent = service.send_message(db_session, live, customer, "whatsapp", approved, values, event_key="b", now=local(12))
    assert sent.status == "sent" and sent.dry_run is False
    out = adapter.calls[0]
    assert out.meta_template_name == "test_order_update" and out.template_values == ["Test Ali", "T-9"] and out.to == "923001234567"

    db_session.add(IncomingMessage(customer_id=customer.id, from_address="+923001234567", provider_message_id="wamid.IN1", message_type="text", body="hello", received_at=local(11)))
    db_session.flush()
    free = send(db_session, customer, plain, settings=live, event_key="c")                      # the customer wrote 1 hour ago: free text is fine
    assert free.status == "sent" and adapter.calls[1].meta_template_name is None


def test_a_marketing_email_needs_a_working_unsubscribe_link_when_really_sending(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer, "email")
    get_row(db_session).dry_run = False
    promo = make_template(db_session, channel="email", category="marketing")
    assert send(db_session, customer, promo, settings=make_settings(messaging_dry_run=False)).error == "no_unsubscribe_link"


def test_dry_run_can_be_forced_by_the_server(db_session):
    from app.services.messaging.settings_store import dry_run_forced, effective_dry_run

    row = get_row(db_session)
    row.dry_run = False
    assert effective_dry_run(make_settings(messaging_dry_run=False), row) is False
    assert effective_dry_run(make_settings(messaging_dry_run=True), row) is True and dry_run_forced(make_settings(messaging_dry_run=True))
    row.dry_run = True
    assert effective_dry_run(Settings(_env_file=None), row) is True                                  # on by default


# --- adapters ---------------------------------------------------------------------------------------------------------------------------------


def test_the_whatsapp_payload_for_a_template_and_for_plain_text():
    template = adapters.whatsapp_payload(Outbound("whatsapp", "923001234567", "x", "ur", meta_template_name="test_t", template_values=["Ali", "T-1"]))
    assert template["type"] == "template" and template["template"]["name"] == "test_t" and template["template"]["language"] == {"code": "ur"}
    assert template["template"]["components"][0]["parameters"] == [{"type": "text", "text": "Ali"}, {"type": "text", "text": "T-1"}]
    text = adapters.whatsapp_payload(Outbound("whatsapp", "923001234567", "Hello", "en"))
    assert text["type"] == "text" and text["text"]["body"] == "Hello" and text["messaging_product"] == "whatsapp"


def test_email_html_is_escaped_and_has_the_unsubscribe_link():
    page = adapters.email_html("Hi <b>Ali</b>\nSecond line", "https://api.test.invalid/api/v1/unsubscribe?token=abc")
    assert "&lt;b&gt;Ali&lt;/b&gt;" in page and "<br>" in page and 'href="https://api.test.invalid/api/v1/unsubscribe?token=abc"' in page
    assert "Unsubscribe" not in adapters.email_html("Hi", None)


def test_the_email_adapter_maps_provider_errors(monkeypatch):
    def failing(settings, to, subject, text, html, headers=None):
        raise ApiError(503, "email_send_failed", "x", {"reason": "timeout"})

    monkeypatch.setattr(adapters.mailer, "send_email", failing)
    result = adapters.EmailAdapter(make_settings()).send(Outbound("email", "test@testcustomer.test", "Hi", subject="S"))
    assert (result.ok, result.error, result.transient) == (False, "email_timeout", True)

    def refused(settings, to, subject, text, html, headers=None):
        raise ApiError(503, "email_send_failed", "x", {"reason": "sender_refused"})

    monkeypatch.setattr(adapters.mailer, "send_email", refused)
    assert adapters.EmailAdapter(make_settings()).send(Outbound("email", "t@testcustomer.test", "Hi")).transient is False

    seen = {}
    monkeypatch.setattr(adapters.mailer, "send_email", lambda settings, to, subject, text, html, headers=None: seen.update(headers=headers, text=text))
    assert adapters.EmailAdapter(make_settings()).send(Outbound("email", "t@testcustomer.test", "Hi", unsubscribe_url="https://u.test.invalid/x")).ok
    assert seen["headers"]["List-Unsubscribe"] == "<https://u.test.invalid/x>" and "Unsubscribe: https://u.test.invalid/x" in seen["text"]


def test_the_dry_run_adapter_sends_nothing_and_masks_the_address(caplog):
    with caplog.at_level("INFO"):
        result = adapters.DryRunAdapter().send(Outbound("whatsapp", "923001234567", "Hello there"))
    assert result.ok and result.provider_id.startswith("dryrun-") and "923001234567" not in caplog.text and "92300***567" in caplog.text


# --- the webhook -------------------------------------------------------------------------------------------------------------------------------


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_the_webhook_signature_is_checked():
    body = b'{"entry":[]}'
    assert webhook.verify_signature("test-app-secret", body, sign("test-app-secret", body))
    assert not webhook.verify_signature("test-app-secret", body, sign("wrong-secret", body))
    assert not webhook.verify_signature("test-app-secret", body + b" ", sign("test-app-secret", body))      # the body was changed
    assert not webhook.verify_signature("test-app-secret", body, None)
    assert not webhook.verify_signature("test-app-secret", body, "sha256=")
    assert not webhook.verify_signature("test-app-secret", body, "md5=abc")
    assert not webhook.verify_signature(None, body, sign("", body))                                          # no secret configured: nothing is accepted
    assert not webhook.verify_signature("", body, sign("", body))


def test_the_verify_token_handshake():
    settings = make_settings(whatsapp_verify_token="test-verify-token")
    assert webhook.verify_challenge(settings, "subscribe", "test-verify-token")
    assert not webhook.verify_challenge(settings, "subscribe", "wrong") and not webhook.verify_challenge(settings, "unsubscribe", "test-verify-token")
    assert not webhook.verify_challenge(make_settings(), "subscribe", "") and not webhook.verify_challenge(make_settings(), "subscribe", None)


def status_payload(wamid, status, code=None):
    entry = {"id": wamid, "status": status, "timestamp": "1773000000"}
    if code:
        entry["errors"] = [{"code": code}]
    return {"entry": [{"changes": [{"value": {"statuses": [entry]}}]}]}


def text_payload(wamid, sender, body):
    return {"entry": [{"changes": [{"value": {"messages": [{"id": wamid, "from": sender, "type": "text", "timestamp": "1773000100", "text": {"body": body}}]}}]}]}


def sent_message(db, customer):
    template = make_template(db)
    opt_in(db, customer)
    message = send(db, customer, template, now=local(12))
    message.provider_message_id = "wamid.TESTSENT"
    return message


def test_status_updates_move_forward_and_never_backward(db_session):
    customer = make_customer(db_session)
    message = sent_message(db_session, customer)
    assert webhook.process_whatsapp_payload(db_session, status_payload("wamid.TESTSENT", "delivered"))["statuses"] == 1
    assert message.status == "delivered" and message.delivered_at is not None
    webhook.process_whatsapp_payload(db_session, status_payload("wamid.TESTSENT", "read"))
    assert message.status == "read" and message.read_at is not None
    webhook.process_whatsapp_payload(db_session, status_payload("wamid.TESTSENT", "sent"))               # a late, older update
    webhook.process_whatsapp_payload(db_session, status_payload("wamid.TESTSENT", "delivered"))
    assert message.status == "read"
    webhook.process_whatsapp_payload(db_session, status_payload("wamid.TESTSENT", "failed", "131026"))    # too late to fail
    assert message.status == "read"
    assert webhook.process_whatsapp_payload(db_session, status_payload("wamid.UNKNOWN", "read"))["statuses"] == 0


def test_a_failed_status_is_recorded_with_the_code(db_session):
    customer = make_customer(db_session)
    message = sent_message(db_session, customer)
    webhook.process_whatsapp_payload(db_session, status_payload("wamid.TESTSENT", "failed", "131026"))
    assert (message.status, message.error) == ("failed", "whatsapp_131026") and message.failed_at is not None


def test_a_reply_marks_the_message_replied_and_is_saved_once(db_session):
    customer = make_customer(db_session)
    message = sent_message(db_session, customer)
    payload = text_payload("wamid.IN-1", "923001234567", "Thanks, got it")
    assert webhook.process_whatsapp_payload(db_session, payload)["incoming"] == 1
    assert webhook.process_whatsapp_payload(db_session, payload)["incoming"] == 0                           # the same delivery again
    assert message.status == "replied" and message.replied_at is not None
    saved = db_session.query(IncomingMessage).one()
    assert (saved.customer_id, saved.from_address, saved.body, saved.is_stop) == (customer.id, "+923001234567", "Thanks, got it", False)


@pytest.mark.parametrize("text", ["STOP", "band karo", "بند کرو"])
def test_stop_opts_the_customer_out_at_once_and_cancels_waiting_messages(db_session, text):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    held = send(db_session, customer, make_template(db_session), now=local(23))               # waiting for the morning
    assert held.status == "queued"
    counts = webhook.process_whatsapp_payload(db_session, text_payload("wamid.IN-STOP", "923001234567", text))
    assert counts["stops"] == 1
    assert consent.consent_state(db_session, customer.id, "whatsapp") == "opted_out"
    assert (held.status, held.error) == ("skipped", "opted_out")
    assert send(db_session, customer, make_template(db_session), event_key="later", now=local(12)).error == "opted_out"
    event = db_session.query(consent.ConsentEvent).filter_by(customer_id=customer.id, action="opt_out").one()
    assert event.source == "whatsapp_stop"


def test_stop_only_affects_whatsapp_and_only_that_customer(db_session):
    a, b = make_customer(db_session), make_customer(db_session, phone="+923009999999", email="b.test@testcustomer.test")
    for customer in (a, b):
        opt_in(db_session, customer)
        opt_in(db_session, customer, "email")
    webhook.process_whatsapp_payload(db_session, text_payload("wamid.IN-S2", "923001234567", "stop"))
    assert consent.consent_state(db_session, a.id, "whatsapp") == "opted_out"
    assert consent.consent_state(db_session, a.id, "email") == "opted_in"
    assert consent.consent_state(db_session, b.id, "whatsapp") == "opted_in"


def test_a_message_from_an_unknown_number_is_kept_but_changes_nothing(db_session):
    counts = webhook.process_whatsapp_payload(db_session, text_payload("wamid.IN-X", "923007777777", "stop"))
    assert counts["incoming"] == 1
    saved = db_session.query(IncomingMessage).one()
    assert saved.customer_id is None and saved.is_stop is True


def test_media_messages_are_recorded_with_their_type(db_session):
    customer = make_customer(db_session)
    payload = {"entry": [{"changes": [{"value": {"messages": [{"id": "wamid.IN-V", "from": "923001234567", "type": "video", "timestamp": "1773000200", "video": {"id": "media-1", "mime_type": "video/mp4"}}]}}]}]}
    webhook.process_whatsapp_payload(db_session, payload)
    saved = db_session.query(IncomingMessage).one()
    assert (saved.message_type, saved.media_id, saved.mime_type, saved.customer_id) == ("video", "media-1", "video/mp4", customer.id)


def test_malformed_webhook_bodies_are_ignored_not_errors(db_session):
    for payload in ({}, {"entry": "x"}, {"entry": [None]}, {"entry": [{"changes": [{"value": {"messages": [{"id": "", "from": "1"}]}}]}]}, []):
        assert webhook.process_whatsapp_payload(db_session, payload) == {"statuses": 0, "incoming": 0, "stops": 0}


def test_unsubscribe_link_opts_the_customer_out_of_email_only(db_session):
    settings = make_settings(messaging_secret="test-secret-for-the-tests")
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    opt_in(db_session, customer, "email")
    token = tokens.make_unsubscribe_token(settings, customer.id, "email")
    assert webhook.unsubscribe(db_session, settings, token) is True
    assert consent.consent_state(db_session, customer.id, "email") == "opted_out" and consent.consent_state(db_session, customer.id, "whatsapp") == "opted_in"
    assert webhook.unsubscribe(db_session, settings, "forged-token") is False
    assert webhook.unsubscribe(db_session, make_settings(), token) is False


def test_json_payload_roundtrip_is_what_meta_sends():
    assert json.loads(json.dumps(status_payload("w", "sent")))["entry"][0]["changes"][0]["value"]["statuses"][0]["id"] == "w"
