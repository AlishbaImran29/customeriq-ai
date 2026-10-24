"""Auto Messenger part 1 over HTTP: settings, test send, templates, consent, the message log, the public webhook
and the unsubscribe link. Everything is made up for the tests."""

import hashlib
import hmac
import io
import json
from datetime import datetime, timezone

import pytest

from app.core.config import Settings, get_settings
from app.main import app
from app.models import Customer, Message
from app.services.messaging import service
from app.services.messaging import tokens as tokens_service
from app.services.messaging.settings_store import get_row

APP_SECRET = "test-app-secret-for-the-tests"
SETTINGS = dict(whatsapp_app_secret=APP_SECRET, whatsapp_verify_token="test-verify-token", messaging_secret="test-secret-for-the-tests", public_api_url="https://api.test.invalid")


def use_settings(**changes):
    values = {**SETTINGS, "messaging_dry_run": True, **changes}
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **values)


def customer(db, phone="+923001234567", email="test.customer@testcustomer.test", name="Test Ali"):
    c = Customer(external_id=f"TEST-{phone}-{email}", first_name=name, phone=phone, phone_normalised=phone, email=email, country="Pakistan")
    db.add(c)
    db.flush()
    return c


BODY = {"name": "test_order_update", "channel": "whatsapp", "category": "utility", "language": "en", "body": "Hello {{first_name}}, your order {{order_number}} is on its way."}


def template(db_client, **changes):
    return db_client.post("/api/v1/messaging/templates", json={**BODY, **changes})


# --- settings ---------------------------------------------------------------------------------------------------------


def test_settings_default_to_dry_run_and_show_connections_without_secrets(db_client):
    use_settings()
    body = db_client.get("/api/v1/messaging/settings").json()
    assert body["dryRun"] is True and body["effectiveDryRun"] is True and body["dryRunForced"] is True
    assert (body["quietStart"], body["quietEnd"], body["timezone"], body["weeklyMarketingCap"]) == ("21:00", "10:00", "Asia/Karachi", 2)
    assert body["whatsapp"]["configured"] is False and body["whatsapp"]["details"]["appSecret"] is True
    assert body["unsubscribeReady"] is True and body["webhookUrl"] == "https://api.test.invalid/api/v1/webhooks/whatsapp"
    assert "test-app-secret" not in json.dumps(body) and "test-verify-token" not in json.dumps(body) and "test-secret-for" not in json.dumps(body)
    assert body["consent"]["whatsapp"] == {"optedIn": 0, "optedOut": 0, "notAsked": 0}


def test_the_seller_can_change_the_settings_and_bad_values_are_refused(db_client):
    use_settings(messaging_dry_run=None)
    changed = db_client.put("/api/v1/messaging/settings", json={"dryRun": False, "quietStart": "22:00", "quietEnd": "09:30", "weeklyMarketingCap": 3,
                                                                  "defaultLanguage": "ur", "storeName": " Test Boutique ", "reviewUrl": "https://example.com/review",
                                                                  "costUtility": 1.5, "costMarketing": 4.25, "holdoutPercent": 15}).json()
    assert (changed["dryRun"], changed["effectiveDryRun"], changed["quietStart"], changed["quietEnd"]) == (False, False, "22:00", "09:30")
    assert (changed["weeklyMarketingCap"], changed["defaultLanguage"], changed["storeName"], changed["costMarketing"], changed["holdoutPercent"]) == (3, "ur", "Test Boutique", 4.25, 15)
    for bad in ({"quietStart": "25:00"}, {"weeklyMarketingCap": 99}, {"reviewUrl": "http://insecure.example"}, {"holdoutPercent": 90}, {"defaultLanguage": "fr"}):
        assert db_client.put("/api/v1/messaging/settings", json=bad).status_code == 422
    assert db_client.put("/api/v1/messaging/settings", json={"quietStart": "10:00", "quietEnd": "10:00"}).status_code == 422


def test_a_server_forced_dry_run_cannot_be_turned_off_in_the_page(db_client):
    use_settings(messaging_dry_run=True)
    response = db_client.put("/api/v1/messaging/settings", json={"dryRun": False})
    assert response.status_code == 409 and response.json()["error"]["code"] == "dry_run_forced"
    assert db_client.put("/api/v1/messaging/settings", json={"dryRun": True}).status_code == 200


# --- test send ---------------------------------------------------------------------------------------------------------------


def test_test_send_in_dry_run_sends_nothing_and_masks_the_number(db_client):
    use_settings()
    sent = db_client.post("/api/v1/messaging/test-send", json={"channel": "whatsapp", "to": "0300 1234567"}).json()
    assert sent["ok"] is True and sent["dryRun"] is True and sent["sentTo"] == "92300***567"
    email = db_client.post("/api/v1/messaging/test-send", json={"channel": "email"}).json()
    assert email["ok"] is True and email["sentTo"].endswith("@example.com")                                   # the signed-in test account's own address
    assert db_client.post("/api/v1/messaging/test-send", json={"channel": "whatsapp", "to": "12345"}).status_code == 422
    assert db_client.post("/api/v1/messaging/test-send", json={"channel": "whatsapp"}).status_code == 422


def test_test_send_is_rate_limited_per_account(db_client):
    import uuid
    from types import SimpleNamespace

    from app.api.deps import require_user
    from app.services.rate_limit import reset_rate_limits

    reset_rate_limits()
    use_settings()
    same = SimpleNamespace(id=uuid.uuid4(), email="test@example.com", name="T")
    app.dependency_overrides[require_user] = lambda: same
    codes = [db_client.post("/api/v1/messaging/test-send", json={"channel": "whatsapp", "to": "03001234567"}).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]
    reset_rate_limits()


# --- templates -----------------------------------------------------------------------------------------------------------------


def test_create_list_and_the_variables_found(db_client):
    created = template(db_client)
    assert created.status_code == 201
    body = created.json()
    assert body["variables"] == ["first_name", "order_number"] and body["approvedBySeller"] is False and body["metaApprovalStatus"] == "not_submitted"
    assert [t["id"] for t in db_client.get("/api/v1/messaging/templates").json()] == [body["id"]]
    assert db_client.get("/api/v1/messaging/templates?channel=email").json() == []
    assert any(v["name"] == "first_name" and v["optional"] is False for v in db_client.get("/api/v1/messaging/variables").json())
    assert template(db_client).status_code == 409                                                                         # the same name, channel and language


def test_template_validation(db_client):
    assert template(db_client, name="bad_vars", body="Hi {{frist_name}}").json()["error"]["code"] == "unknown_variable"
    assert template(db_client, name="email_without_subject", channel="email").status_code == 422
    assert template(db_client, name="x").status_code == 422
    assert template(db_client, name="empty_body", body="   ").status_code == 422
    ok = template(db_client, name="email_ok", channel="email", subject="Order {{order_number}}")
    assert ok.status_code == 201 and ok.json()["subject"] == "Order {{order_number}}"
    assert template(db_client, name="wa_subject_dropped", subject="ignored").json()["subject"] is None


def test_approving_is_the_sellers_decision_and_editing_the_wording_withdraws_it(db_client):
    t = template(db_client).json()
    approved = db_client.post(f"/api/v1/messaging/templates/{t['id']}/approve").json()
    assert approved["approvedBySeller"] is True and approved["approvedAt"] is not None
    meta = db_client.patch(f"/api/v1/messaging/templates/{t['id']}", json={"metaTemplateName": "order_update", "metaApprovalStatus": "approved"}).json()
    assert meta["approvedBySeller"] is True and meta["metaApprovalStatus"] == "approved"                           # meta fields do not withdraw approval
    edited = db_client.patch(f"/api/v1/messaging/templates/{t['id']}", json={"body": "Hello {{first_name}}, a new wording for {{order_number}}."}).json()
    assert edited["approvedBySeller"] is False and edited["approvedAt"] is None and edited["metaApprovalStatus"] == "not_submitted"
    assert db_client.patch(f"/api/v1/messaging/templates/{t['id']}", json={"body": "Hi {{nope}}"}).status_code == 422
    assert db_client.post(f"/api/v1/messaging/templates/{t['id']}/approve").json()["approvedBySeller"] is True
    assert db_client.post(f"/api/v1/messaging/templates/{t['id']}/unapprove").json()["approvedBySeller"] is False
    assert db_client.post("/api/v1/messaging/templates/999999/approve").status_code == 404


def test_a_whatsapp_marketing_template_must_tell_people_how_to_stop(db_client):
    t = template(db_client, name="promo", category="marketing", body="TEST offer for {{first_name}}.").json()
    refused = db_client.post(f"/api/v1/messaging/templates/{t['id']}/approve")
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "needs_stop_instruction"
    db_client.patch(f"/api/v1/messaging/templates/{t['id']}", json={"body": "TEST offer for {{first_name}}. Reply STOP to stop messages."})
    assert db_client.post(f"/api/v1/messaging/templates/{t['id']}/approve").status_code == 200
    email = template(db_client, name="promo_mail", channel="email", category="marketing", subject="Offer", body="TEST offer for {{first_name}}.").json()
    assert db_client.post(f"/api/v1/messaging/templates/{email['id']}/approve").status_code == 200                # email gets an automatic unsubscribe footer


def test_preview_shows_example_values_and_the_meta_form(db_client):
    shown = db_client.post("/api/v1/messaging/templates/preview", json={"body": "Hi {{first_name}}, order {{order_number}}. {{cod_note}}", "language": "ur"}).json()
    assert shown["label"] == "Example values, not a real customer" and "علی" in shown["text"] and "ORD-1001" in shown["text"] and shown["error"] is None
    assert shown["metaBody"] == "Hi {{1}}, order {{2}}. {{3}}" and shown["metaVariables"] == ["first_name", "order_number", "cod_note"]
    bad = db_client.post("/api/v1/messaging/templates/preview", json={"body": "Hi {{oops}}"}).json()
    assert bad["text"] is None and "Unknown variable" in bad["error"]


def test_delete_a_template(db_client):
    t = template(db_client).json()
    assert db_client.delete(f"/api/v1/messaging/templates/{t['id']}").status_code == 204
    assert db_client.get("/api/v1/messaging/templates").json() == []


# --- consent ------------------------------------------------------------------------------------------------------------------------


def test_consent_list_search_filter_and_change(db_client, db_session):
    a, b = customer(db_session, name="Test Ali"), customer(db_session, "+923009999999", "b.test@testcustomer.test", "Test Sara")
    page = db_client.get("/api/v1/messaging/consent").json()
    assert page["total"] == 2 and page["customers"][0]["whatsapp"]["state"] == "none"
    assert [c["name"] for c in db_client.get("/api/v1/messaging/consent?search=sara").json()["customers"]] == ["Test Sara"]
    assert db_client.get("/api/v1/messaging/consent?search=%25%25").json()["total"] == 0                          # a % is a letter, not a wildcard

    changed = db_client.patch(f"/api/v1/messaging/consent/{a.id}", json={"channel": "whatsapp", "optedIn": True, "note": "Asked in the shop"}).json()
    assert changed["whatsapp"]["state"] == "opted_in" and changed["whatsapp"]["source"] == "manual" and changed["emailConsent"]["state"] == "none"
    assert [c["id"] for c in db_client.get("/api/v1/messaging/consent?channel=whatsapp&state=opted_in").json()["customers"]] == [a.id]
    assert [c["id"] for c in db_client.get("/api/v1/messaging/consent?channel=whatsapp&state=none").json()["customers"]] == [b.id]
    db_client.patch(f"/api/v1/messaging/consent/{a.id}", json={"channel": "whatsapp", "optedIn": False})
    assert db_client.get("/api/v1/messaging/consent?channel=whatsapp&state=opted_out").json()["total"] == 1
    history = db_client.get(f"/api/v1/messaging/consent/{a.id}/history").json()
    assert [h["action"] for h in history] == ["opt_out", "opt_in"] and history[1]["note"] == "Asked in the shop"
    assert db_client.patch("/api/v1/messaging/consent/999999", json={"channel": "email", "optedIn": True}).status_code == 404
    assert db_client.patch(f"/api/v1/messaging/consent/{a.id}", json={"channel": "sms", "optedIn": True}).status_code == 422
    assert db_client.get("/api/v1/messaging/settings").json()["consent"]["whatsapp"] == {"optedIn": 0, "optedOut": 1, "notAsked": 1}


def import_file(db_client, text, confirm=True):
    return db_client.post("/api/v1/messaging/consent/import", data={"confirm": "true" if confirm else "false"}, files={"file": ("consent.csv", io.BytesIO(text.encode()), "text/csv")})


def test_consent_import_needs_confirmation_and_records_only_what_the_file_says(db_client, db_session):
    a = customer(db_session)
    b = customer(db_session, "+923008888888", "sara.test@testcustomer.test", "Test Sara")
    csv_text = (
        "phone,email,channel,opted_in,date,source\n"
        "0300 1234567,,whatsapp,yes,2026-02-01,paper form\n"
        ",sara.test@testcustomer.test,email,yes,,\n"
        "0300 7777777,,whatsapp,yes,,\n"
        "0300 1234567,,whatsapp,maybe,,\n"
        "0300 1234567,,telegram,yes,,\n"
        "0300 1234567,,whatsapp,yes,not-a-date,\n"
    )
    assert import_file(db_client, csv_text, confirm=False).status_code == 422
    result = import_file(db_client, csv_text).json()
    assert (result["rowsInFile"], result["changed"], result["notFound"], result["rejected"]) == (6, 2, 1, 3)
    assert {e["column"] for e in result["errors"]} == {"opted_in", "channel", "date"}
    page = {c["id"]: c for c in db_client.get("/api/v1/messaging/consent").json()["customers"]}
    assert page[a.id]["whatsapp"] == {"state": "opted_in", "changedOn": "2026-02-01", "source": "paper form"}
    assert page[b.id]["emailConsent"]["state"] == "opted_in" and page[b.id]["emailConsent"]["source"] == "import"
    again = import_file(db_client, csv_text).json()
    assert again["changed"] == 0 and again["unchanged"] == 2                                                              # importing twice changes nothing
    assert import_file(db_client, "name,age\nAli,3\n").status_code == 422


# --- the message log and the queue ------------------------------------------------------------------------------------------------------


def test_the_message_log_shows_sent_and_skipped_messages_with_the_reason(db_client, db_session):
    use_settings()
    a, b = customer(db_session), customer(db_session, "+923008888888", "b.test@testcustomer.test", "Test Sara")
    t = template(db_client).json()
    db_client.post(f"/api/v1/messaging/templates/{t['id']}/approve")
    db_client.patch(f"/api/v1/messaging/consent/{a.id}", json={"channel": "whatsapp", "optedIn": True})
    from app.models import MessageTemplate

    row = db_session.get(MessageTemplate, t["id"])
    for who, key in ((a, "k1"), (b, "k2")):
        service.send_message(db_session, Settings(_env_file=None, messaging_dry_run=True), who, "whatsapp", row,
                             service.customer_variables(who, get_row(db_session), "en", {"order_number": "T-1"}), event_key=key, now=datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc))        # 12:00 in Pakistan: not in quiet hours
    db_session.flush()
    log = db_client.get("/api/v1/messaging/messages").json()
    by_name = {m["customerName"]: m for m in log}
    assert by_name["Test Ali"]["status"] == "sent" and by_name["Test Ali"]["dryRun"] is True and "T-1" in by_name["Test Ali"]["text"]
    assert by_name["Test Sara"]["status"] == "skipped" and by_name["Test Sara"]["error"] == "no_consent"
    assert [m["customerName"] for m in db_client.get("/api/v1/messaging/messages?status=skipped").json()] == ["Test Sara"]
    assert db_client.get("/api/v1/messaging/messages?status=bogus").status_code == 422


def test_process_queue_endpoint(db_client):
    use_settings()
    assert db_client.post("/api/v1/messaging/process-queue").json() == {"processed": 0, "sent": 0, "requeued": 0, "failed": 0, "skipped": 0}


# --- the public webhook -------------------------------------------------------------------------------------------------------------------


def signed(payload: dict) -> tuple[bytes, dict]:
    body = json.dumps(payload).encode()
    return body, {"X-Hub-Signature-256": "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest(), "Content-Type": "application/json"}


def stop_payload(wamid="wamid.API-STOP", text="STOP"):
    return {"entry": [{"changes": [{"value": {"messages": [{"id": wamid, "from": "923001234567", "type": "text", "timestamp": "1773000100", "text": {"body": text}}]}}]}]}


def test_the_webhook_handshake(db_client):
    use_settings()
    ok = db_client.get("/api/v1/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "test-verify-token", "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345"
    assert db_client.get("/api/v1/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"}).status_code == 403
    assert db_client.get("/api/v1/webhooks/whatsapp").status_code == 403


def test_the_webhook_refuses_a_missing_or_wrong_signature_and_changes_nothing(db_client, db_session):
    use_settings()
    a = customer(db_session)
    db_client.patch(f"/api/v1/messaging/consent/{a.id}", json={"channel": "whatsapp", "optedIn": True})
    body, headers = signed(stop_payload())
    assert db_client.post("/api/v1/webhooks/whatsapp", content=body).status_code == 403                          # no signature
    assert db_client.post("/api/v1/webhooks/whatsapp", content=body, headers={**headers, "X-Hub-Signature-256": "sha256=" + "0" * 64}).status_code == 403
    assert db_client.post("/api/v1/webhooks/whatsapp", content=body + b" ", headers=headers).status_code == 403          # the body was changed after signing
    page = db_client.get("/api/v1/messaging/consent?channel=whatsapp&state=opted_in").json()
    assert page["total"] == 1                                                                                          # still opted in: nothing happened
    use_settings(whatsapp_app_secret=None)
    assert db_client.post("/api/v1/webhooks/whatsapp", content=body, headers=headers).status_code == 403              # no secret configured: nothing is accepted


def test_a_signed_stop_opts_the_customer_out(db_client, db_session):
    use_settings()
    a = customer(db_session)
    db_client.patch(f"/api/v1/messaging/consent/{a.id}", json={"channel": "whatsapp", "optedIn": True})
    body, headers = signed(stop_payload())
    response = db_client.post("/api/v1/webhooks/whatsapp", content=body, headers=headers)
    assert response.status_code == 200 and response.json() == {"ok": True, "statuses": 0, "incoming": 1, "stops": 1}
    assert db_client.get("/api/v1/messaging/consent?channel=whatsapp&state=opted_out").json()["total"] == 1
    assert db_client.post("/api/v1/webhooks/whatsapp", content=body, headers=headers).json()["incoming"] == 0         # Meta retries: not saved twice
    assert [i["isStop"] for i in db_client.get("/api/v1/messaging/incoming").json()] == [True]


def test_a_signed_body_that_is_not_json_is_a_400(db_client):
    use_settings()
    body = b"not json"
    headers = {"X-Hub-Signature-256": "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()}
    assert db_client.post("/api/v1/webhooks/whatsapp", content=body, headers=headers).status_code == 400


def test_the_webhook_needs_no_sign_in_but_the_rest_does(db_client):
    from app.api.deps import require_user

    app.dependency_overrides.pop(require_user, None)
    use_settings()
    body, headers = signed({"entry": []})
    assert db_client.post("/api/v1/webhooks/whatsapp", content=body, headers=headers).status_code == 200
    assert db_client.get("/api/v1/messaging/settings").status_code == 401
    assert db_client.get("/api/v1/messaging/consent").status_code == 401


# --- the unsubscribe link -----------------------------------------------------------------------------------------------------------------


def test_the_unsubscribe_link_works_by_get_and_by_one_click_post(db_client, db_session):
    use_settings()
    a = customer(db_session)
    db_client.patch(f"/api/v1/messaging/consent/{a.id}", json={"channel": "email", "optedIn": True})
    settings = Settings(_env_file=None, **SETTINGS)
    token = tokens_service.make_unsubscribe_token(settings, a.id, "email")
    page = db_client.get("/api/v1/unsubscribe", params={"token": token})
    assert page.status_code == 200 and "You are unsubscribed" in page.text
    assert db_client.get("/api/v1/messaging/consent?channel=email&state=opted_out").json()["total"] == 1
    assert db_client.get("/api/v1/unsubscribe", params={"token": "forged-token-value"}).status_code == 400
    b = customer(db_session, "+923008888888", "b.test@testcustomer.test")
    db_client.patch(f"/api/v1/messaging/consent/{b.id}", json={"channel": "email", "optedIn": True})
    assert db_client.post("/api/v1/unsubscribe", params={"token": tokens_service.make_unsubscribe_token(settings, b.id, "email")}).json() == {"ok": True}
    assert db_client.post("/api/v1/unsubscribe", params={"token": "forged-token-value"}).status_code == 400
    assert db_client.get("/api/v1/messaging/consent?channel=email&state=opted_in").json()["total"] == 0


# --- demo helpers -----------------------------------------------------------------------------------------------------------------------------


def test_the_demo_helpers_work_in_development_and_are_hidden_in_production(db_client, db_session):
    use_settings(app_env="development")
    a = customer(db_session)
    db_client.patch(f"/api/v1/messaging/consent/{a.id}", json={"channel": "whatsapp", "optedIn": True})
    simulated = db_client.post("/api/v1/messaging/dev/simulate-incoming", json={"phone": "0300 1234567", "text": "band karo"}).json()
    assert simulated["stops"] == 1 and db_client.get("/api/v1/messaging/consent?channel=whatsapp&state=opted_out").json()["total"] == 1
    use_settings(app_env="production")
    assert db_client.post("/api/v1/messaging/dev/simulate-incoming", json={"phone": "0300 1234567", "text": "stop"}).status_code == 404
    assert db_client.post("/api/v1/messaging/dev/simulate-status", json={"messageId": 1, "status": "read"}).status_code == 404
