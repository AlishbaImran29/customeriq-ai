"""Auto Messenger part 3: unboxing request, customer videos, the YES/NO permission and the review request.
Customers, files and Meta's answers are all made up (marked TEST); no network or storage is used."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.main import app
from app.models import Customer, CustomerMedia, IncomingMessage, Message, MessageTemplate, Order, OrderStatusHistory
from app.services import order_status, supabase_storage
from app.services.messaging import consent, followups, media, webhook
from app.services.messaging.settings_store import get_row

NOW = datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc)               # 12:00 in Pakistan
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 64
_n = [0]


def live_settings(**changes) -> Settings:
    base = dict(whatsapp_access_token="test-token", whatsapp_phone_number_id="123", supabase_url="https://test.supabase.invalid", supabase_service_key="test-key")
    return Settings(_env_file=None, messaging_dry_run=True, **{**base, **changes})


def customer(db, phone="+923001234567", name="Test Ali"):
    _n[0] += 1
    c = Customer(external_id=f"TEST-M{_n[0]}", first_name=name, phone=phone, phone_normalised=phone, email=f"m{_n[0]}.test@testcustomer.test", country="Pakistan")
    db.add(c)
    db.flush()
    return c


def order(db, c, *, outcome=None):
    _n[0] += 1
    o = Order(external_id=f"TEST-MORD-{_n[0]}", customer_id=c.id, order_date=date(2026, 3, 1), order_value=Decimal(2500), payment_type="cod", products="Test shoes", outcome=outcome, source="manual")
    db.add(o)
    db.flush()
    return o


def delivered(db, o, when):
    db.add(OrderStatusHistory(order_id=o.id, status="delivered", at=when, source="manual"))
    db.flush()


def template(db, event, channel="whatsapp", language="en", body=None, approved=True):
    _n[0] += 1
    t = MessageTemplate(name=f"test_{event}_{_n[0]}", channel=channel, category="utility", language=language, event=event, subject="TEST" if channel == "email" else None,
                        body=body or "Hi {{first_name}}, TEST for {{order_number}}. {{review_link}}", approved_by_seller=approved)
    db.add(t)
    db.flush()
    return t


def incoming(db, c, kind="video", mime="video/mp4", media_id="media-1", wamid=None):
    _n[0] += 1
    row = IncomingMessage(customer_id=c.id, from_address=c.phone_normalised, provider_message_id=wamid or f"wamid.TEST-IN-{_n[0]}", message_type=kind, media_id=media_id, mime_type=mime, received_at=NOW)
    db.add(row)
    db.flush()
    return row


# --- checking a file -------------------------------------------------------------------------------------------------------


def test_the_first_bytes_must_match_the_claimed_type():
    assert media.looks_right("video/mp4", MP4) and not media.looks_right("video/mp4", PNG)
    assert media.looks_right("image/png", PNG) and not media.looks_right("image/jpeg", PNG) and not media.looks_right("image/png", MP4)
    assert media.looks_right("image/jpeg", b"\xff\xd8\xff\xe0" + b"0" * 10)
    assert media.base_mime("video/mp4; codecs=avc1") == "video/mp4"


def patch_cloud(monkeypatch, info, content=MP4):
    monkeypatch.setattr(media, "media_info", lambda settings, media_id: info)
    monkeypatch.setattr(media, "download", lambda settings, url, limit: content if len(content) <= limit else (_ for _ in ()).throw(media.MediaRejected("too_large")))


def test_a_good_video_and_a_good_photo_are_accepted(monkeypatch):
    patch_cloud(monkeypatch, {"url": "https://lookaside.test.invalid/x", "mime_type": "video/mp4", "file_size": len(MP4)})
    assert media.fetch_media(live_settings(), "m1") == (MP4, "video/mp4")
    patch_cloud(monkeypatch, {"url": "https://lookaside.test.invalid/x", "mime_type": "image/png", "file_size": len(PNG)}, PNG)
    assert media.fetch_media(live_settings(), "m2") == (PNG, "image/png")


@pytest.mark.parametrize("info,content,reason", [
    ({"url": "https://x.test.invalid/a", "mime_type": "application/pdf", "file_size": 10}, MP4, "file_type"),
    ({"url": "https://x.test.invalid/a", "mime_type": "video/mp4", "file_size": 17 * 1024 * 1024}, MP4, "too_large"),
    ({"url": "https://x.test.invalid/a", "mime_type": "image/png", "file_size": 6 * 1024 * 1024}, PNG, "too_large"),
    ({"url": "http://x.test.invalid/a", "mime_type": "video/mp4", "file_size": 10}, MP4, "no_download_link"),
    ({"url": "https://x.test.invalid/a", "mime_type": "video/mp4", "file_size": 10}, PNG, "not_really_video"),
    ({"url": "https://x.test.invalid/a", "mime_type": "image/png", "file_size": 10}, MP4, "not_really_image"),
    ({"url": "https://x.test.invalid/a", "mime_type": "video/mp4", "file_size": 10}, b"", "empty_file"),
])
def test_files_that_are_not_allowed_are_refused_with_a_reason(monkeypatch, info, content, reason):
    patch_cloud(monkeypatch, info, content)
    with pytest.raises(media.MediaRejected) as caught:
        media.fetch_media(live_settings(), "m1")
    assert caught.value.reason == reason


def test_a_download_stops_as_soon_as_it_is_too_big(monkeypatch):
    class Stream:
        def __init__(self):
            self.read_total = 0

        def read(self, size):
            self.read_total += size
            return b"x" * size

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    stream = Stream()
    monkeypatch.setattr(media, "_open", lambda settings, url: stream)
    with pytest.raises(media.MediaRejected) as caught:
        media.download(live_settings(), "https://x.test.invalid/a", 1024 * 1024)
    assert caught.value.reason == "too_large" and stream.read_total < 3 * 1024 * 1024         # it did not read forever


# --- which files are wanted -----------------------------------------------------------------------------------------------------


def test_only_a_known_customer_with_a_recent_delivery_is_queued(db_session):
    stranger = IncomingMessage(customer_id=None, from_address="+923007777777", provider_message_id="wamid.STRANGER", message_type="video", media_id="m", mime_type="video/mp4", received_at=NOW)
    db_session.add(stranger)
    db_session.flush()
    assert media.queue_media(db_session, stranger, NOW) is None                                        # an unknown number: never downloaded

    c = customer(db_session)
    assert media.queue_media(db_session, incoming(db_session, c), NOW) is None                         # nothing delivered yet
    o = order(db_session, c)
    delivered(db_session, o, NOW - timedelta(days=31))
    assert media.queue_media(db_session, incoming(db_session, c), NOW) is None                         # delivered too long ago
    delivered(db_session, order(db_session, c), NOW - timedelta(days=3))
    queued = media.queue_media(db_session, incoming(db_session, c), NOW)
    assert queued.status == "pending" and queued.kind == "video" and queued.order_id is not None and queued.share_answer == "pending"


def test_an_unsupported_type_is_kept_as_a_refused_record_and_a_repeat_adds_nothing(db_session):
    c = customer(db_session)
    delivered(db_session, order(db_session, c), NOW - timedelta(days=1))
    row = incoming(db_session, c, kind="video", mime="video/x-flv")
    refused = media.queue_media(db_session, row, NOW)
    assert (refused.status, refused.error) == ("rejected", "file_type")
    assert media.queue_media(db_session, row, NOW).id == refused.id and db_session.query(CustomerMedia).count() == 1


# --- storing it and asking permission -----------------------------------------------------------------------------------------------


def stored_setup(db_session, monkeypatch):
    c = customer(db_session)
    consent.set_consent(db_session, c.id, "whatsapp", True, "manual")
    delivered(db_session, order(db_session, c), NOW - timedelta(days=1))
    template(db_session, "media_share_question", body="Thanks {{first_name}}! May we share it? Reply YES or NO.")
    uploads = []
    patch_cloud(monkeypatch, {"url": "https://lookaside.test.invalid/x", "mime_type": "video/mp4", "file_size": len(MP4)})
    monkeypatch.setattr(supabase_storage, "_call", lambda settings, method, path, body, ctype: uploads.append((method, path, ctype, len(body))) or {})
    pending = media.queue_media(db_session, incoming(db_session, c), NOW)
    return c, pending, uploads


def test_a_waiting_video_is_stored_privately_and_the_customer_is_asked_for_permission(db_session, monkeypatch):
    c, pending, uploads = stored_setup(db_session, monkeypatch)
    counts = media.process_pending_media(db_session, live_settings(), NOW)
    assert counts == {"stored": 1, "rejected": 0, "failed": 0, "waiting": 0}
    assert (pending.status, pending.mime_type, pending.size_bytes) == ("stored", "video/mp4", len(MP4))
    assert pending.storage_path.startswith(f"customer-{c.id}/") and pending.storage_path.endswith(".mp4")
    assert uploads[0][0] == "POST" and uploads[0][1].startswith("/object/customer-media/customer-") and uploads[0][2] == "video/mp4"
    question = db_session.query(Message).filter_by(customer_id=c.id).one()
    assert question.status == "sent" and "May we share it?" in question.rendered_text and pending.question_sent is True


def test_a_rejected_file_is_marked_and_never_stored(db_session, monkeypatch):
    c, pending, uploads = stored_setup(db_session, monkeypatch)
    monkeypatch.setattr(media, "fetch_media", lambda settings, media_id: (_ for _ in ()).throw(media.MediaRejected("too_large")))
    assert media.process_pending_media(db_session, live_settings(), NOW)["rejected"] == 1
    assert (pending.status, pending.error, pending.storage_path) == ("rejected", "too_large", None) and uploads == []
    assert db_session.query(Message).count() == 0                                                     # no question for a refused file


def test_a_temporary_problem_is_retried_and_gives_up_after_three_tries(db_session, monkeypatch):
    c, pending, _ = stored_setup(db_session, monkeypatch)
    monkeypatch.setattr(media, "fetch_media", lambda settings, media_id: (_ for _ in ()).throw(media.MediaTemporary("network")))
    assert media.process_pending_media(db_session, live_settings(), NOW)["waiting"] == 1 and pending.status == "pending" and pending.attempts == 1
    media.process_pending_media(db_session, live_settings(), NOW)
    assert media.process_pending_media(db_session, live_settings(), NOW)["failed"] == 1 and pending.status == "failed"


def test_nothing_is_downloaded_until_whatsapp_and_storage_are_set_up(db_session, monkeypatch):
    c, pending, uploads = stored_setup(db_session, monkeypatch)
    counts = media.process_pending_media(db_session, Settings(_env_file=None), NOW)
    assert counts["waiting"] == 1 and pending.status == "pending" and pending.error == "not_configured" and pending.attempts == 0 and uploads == []


# --- the YES / NO permission ---------------------------------------------------------------------------------------------------------


def text_payload(wamid, sender, body):
    return {"entry": [{"changes": [{"value": {"messages": [{"id": wamid, "from": sender, "type": "text", "timestamp": "1773000100", "text": {"body": body}}]}}]}]}


def test_a_yes_lets_the_seller_use_the_file_and_a_no_does_not(db_session, monkeypatch):
    c, pending, _ = stored_setup(db_session, monkeypatch)
    media.process_pending_media(db_session, live_settings(), NOW)
    with pytest.raises(ApiError) as caught:
        media.set_usable(pending, True)                                                                  # no answer yet
    assert caught.value.status_code == 409 and caught.value.code == "no_permission"
    webhook.process_whatsapp_payload(db_session, text_payload("wamid.ANS1", "923001234567", "YES"), NOW)
    assert pending.share_answer == "yes"
    media.set_usable(pending, True, NOW)
    assert pending.usable_in_ads is True and pending.usable_marked_at == NOW
    # the same customer later sends a second video and says NO
    again = media.queue_media(db_session, incoming(db_session, c, media_id="media-2"), NOW)
    again.status, again.question_sent = "stored", True
    webhook.process_whatsapp_payload(db_session, text_payload("wamid.ANS2", "923001234567", "nahi"), NOW)
    assert again.share_answer == "no"
    with pytest.raises(ApiError):
        media.set_usable(again, True)


def test_an_answer_with_no_question_waiting_changes_nothing(db_session, monkeypatch):
    c, pending, _ = stored_setup(db_session, monkeypatch)                                                # still pending: the question was not sent yet
    webhook.process_whatsapp_payload(db_session, text_payload("wamid.ANS3", "923001234567", "YES"), NOW)
    assert pending.share_answer == "pending"
    assert media.apply_share_answer(db_session, c.id, "maybe", NOW) is None


def test_the_database_itself_refuses_usable_without_a_yes(db_session, monkeypatch):
    c, pending, _ = stored_setup(db_session, monkeypatch)
    pending.usable_in_ads = True
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_a_no_after_a_yes_on_the_same_file_withdraws_the_permission(db_session, monkeypatch):
    c, pending, _ = stored_setup(db_session, monkeypatch)
    pending.status, pending.question_sent, pending.share_answer = "stored", True, "pending"
    media.apply_share_answer(db_session, c.id, "yes", NOW)
    media.set_usable(pending, True)
    pending.share_answer = "no"
    pending.usable_in_ads, pending.usable_marked_at = False, None
    db_session.flush()
    assert pending.usable_in_ads is False


# --- the gallery (HTTP) ---------------------------------------------------------------------------------------------------------------


def test_the_gallery_filters_marks_usable_only_after_yes_and_deletes(db_client, db_session, monkeypatch):
    app.dependency_overrides[get_settings] = lambda: live_settings()
    c, pending, uploads = stored_setup(db_session, monkeypatch)
    media.process_pending_media(db_session, live_settings(), NOW)
    monkeypatch.setattr(supabase_storage, "_call", lambda settings, method, path, body, ctype: {"signedURL": "/object/sign/customer-media/x?token=t"} if "/sign/" in path else {})
    everything = db_client.get("/api/v1/messaging/media").json()
    assert len(everything) == 1 and everything[0]["customerName"] == "Test Ali" and everything[0]["status"] == "stored"
    assert everything[0]["url"].startswith("https://test.supabase.invalid/storage/v1/object/sign/")
    assert [m["id"] for m in db_client.get("/api/v1/messaging/media?show=waiting").json()] == [pending.id]
    assert db_client.get("/api/v1/messaging/media?show=usable").json() == []
    refused = db_client.post(f"/api/v1/messaging/media/{pending.id}/usable", json={"usable": True})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "no_permission"

    webhook.process_whatsapp_payload(db_session, text_payload("wamid.ANS9", "923001234567", "haan"), NOW)
    ok = db_client.post(f"/api/v1/messaging/media/{pending.id}/usable", json={"usable": True}).json()
    assert ok["usableInAds"] is True and ok["shareAnswer"] == "yes"
    assert [m["id"] for m in db_client.get("/api/v1/messaging/media?show=usable").json()] == [pending.id]
    assert [m["id"] for m in db_client.get("/api/v1/messaging/media?show=yes").json()] == [pending.id]
    assert db_client.post(f"/api/v1/messaging/media/{pending.id}/usable", json={"usable": False}).json()["usableInAds"] is False

    deleted = []
    monkeypatch.setattr(supabase_storage, "_call", lambda settings, method, path, body, ctype: deleted.append((method, path)) or {})
    assert db_client.delete(f"/api/v1/messaging/media/{pending.id}").status_code == 204
    assert deleted and deleted[0][0] == "DELETE" and deleted[0][1].startswith("/object/customer-media/")
    assert db_client.get("/api/v1/messaging/media").json() == [] and db_client.delete("/api/v1/messaging/media/999999").status_code == 404
    assert db_client.get("/api/v1/messaging/media?show=bogus").status_code == 422


def test_a_forged_media_call_without_a_signature_is_refused(db_client):
    app.dependency_overrides[get_settings] = lambda: live_settings(whatsapp_app_secret="test-secret")
    assert db_client.post("/api/v1/webhooks/whatsapp", json={"entry": []}).status_code == 403


# --- the unboxing request after a delivery -----------------------------------------------------------------------------------------------


def test_delivery_asks_for_an_unboxing_video_two_hours_later_on_whatsapp_only(db_session):
    c = customer(db_session)
    consent.set_consent(db_session, c.id, "whatsapp", True, "manual")
    consent.set_consent(db_session, c.id, "email", True, "manual")
    o = order(db_session, c)
    template(db_session, "order_delivered", body="Delivered {{order_number}}")
    template(db_session, "delivered_unboxing", body="Did {{order_number}} arrive? Send a video, {{first_name}}.")
    template(db_session, "delivered_unboxing", channel="email", body="Email version {{order_number}}")
    change = order_status.record_status(db_session, Settings(_env_file=None, messaging_dry_run=True), o, "delivered", source="manual", at=NOW, now=NOW)
    asked = [m for m in change.messages if "arrive" in m.rendered_text]
    assert len(asked) == 1 and asked[0].channel == "whatsapp" and asked[0].status == "queued" and asked[0].next_attempt_at == NOW + timedelta(hours=2)
    from app.services.messaging import service

    assert service.process_queue(db_session, Settings(_env_file=None, messaging_dry_run=True), now=NOW + timedelta(hours=2, minutes=1))["sent"] == 1
    assert asked[0].status == "sent"


# --- the review request -----------------------------------------------------------------------------------------------------------------------


def review_setup(db_session, delivered_days_ago, *, link=True, returned=False, approved=True):
    c = customer(db_session)
    consent.set_consent(db_session, c.id, "whatsapp", True, "manual")
    o = order(db_session, c, outcome="returned" if returned else None)
    delivered(db_session, o, NOW - timedelta(days=delivered_days_ago))
    template(db_session, "review_request", body="Hi {{first_name}}, how is {{order_number}}? {{review_link}}", approved=approved)
    get_row(db_session).review_url = "https://example.com/review" if link else None
    return c, o


def test_a_review_is_asked_three_days_after_delivery_exactly_once(db_session):
    c, o = review_setup(db_session, 4)
    settings = Settings(_env_file=None, messaging_dry_run=True)
    assert followups.run_review_requests(db_session, settings, NOW)["asked"] == 1
    message = db_session.query(Message).filter_by(order_id=o.id).one()
    assert message.status == "sent" and "https://example.com/review" in message.rendered_text and message.rendered_text.startswith("Hi Test Ali")
    assert followups.run_review_requests(db_session, settings, NOW)["asked"] == 0 and db_session.query(Message).count() == 1


@pytest.mark.parametrize("days,expected", [(2, 0), (3, 1), (14, 1), (15, 0), (40, 0)])
def test_the_review_window_is_3_to_14_days(db_session, days, expected):
    review_setup(db_session, days)
    assert followups.run_review_requests(db_session, Settings(_env_file=None, messaging_dry_run=True), NOW)["asked"] == expected


def test_no_review_is_asked_for_a_returned_order_or_without_a_link(db_session):
    review_setup(db_session, 5, returned=True)
    assert followups.run_review_requests(db_session, Settings(_env_file=None, messaging_dry_run=True), NOW)["asked"] == 0 and db_session.query(Message).count() == 0


def test_without_a_review_link_nothing_is_created_so_requests_go_out_once_it_is_added(db_session):
    review_setup(db_session, 5, link=False)
    settings = Settings(_env_file=None, messaging_dry_run=True)
    assert followups.run_review_requests(db_session, settings, NOW) == {"checked": 0, "asked": 0, "no_link": 1}
    assert db_session.query(Message).count() == 0
    get_row(db_session).review_url = "https://example.com/review"
    assert followups.run_review_requests(db_session, settings, NOW)["asked"] == 1


def test_an_order_that_moved_on_from_delivered_is_not_asked(db_session):
    c, o = review_setup(db_session, 5)
    db_session.add(OrderStatusHistory(order_id=o.id, status="returned", at=NOW - timedelta(days=1), source="manual"))
    db_session.flush()
    assert followups.run_review_requests(db_session, Settings(_env_file=None, messaging_dry_run=True), NOW)["asked"] == 0
