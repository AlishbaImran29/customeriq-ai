"""Email Automations: COD confirmation emails and their buttons, win-back, new-product, personalisation and the sending rules.
Customers are made up (marked TEST); with no Brevo key nothing leaves the server (emails are logged as "mock")."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import CatalogProduct, CodEmail, Customer, EmailAnnouncement, EmailLog, Order
from app.services.email_auto import render as r
from app.services.email_auto import service as svc
from app.services.messaging import consent

NOW = datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc)
_n = [0]


def conf(**changes) -> Settings:
    base = dict(messaging_secret="x" * 32, public_api_url="http://api.test", sender_email="shop@example.com", sender_name="Test Shop", app_url="https://shop.test")
    return Settings(_env_file=None, **{**base, **changes})


def person(db, first="ayesha", email=None, consented=True):
    _n[0] += 1
    c = Customer(external_id=f"TEST-EA{_n[0]}", first_name=first, email=email or f"test{_n[0]}@testcustomer.test", country="Pakistan")
    db.add(c)
    db.flush()
    if consented:
        consent.set_consent(db, c.id, "email", True, "manual")
    return c


def order(db, customer, *, days_ago=1, payment="cod", products="Test Shoes", category="Shoes", value=3500, city="Lahore"):
    _n[0] += 1
    o = Order(external_id=f"TEST-EAO{_n[0]}", customer_id=customer.id, order_date=NOW.date() - timedelta(days=days_ago), order_value=Decimal(value), payment_type=payment,
              products=products, product_category=category, city=city, source="manual")
    db.add(o)
    db.flush()
    return o


def product(db, name="Test Boots", category="Shoes", price=4500, image="https://img.test/a.png"):
    p = CatalogProduct(name=name, category=category, price=price, source="manual", image_url=image)
    db.add(p)
    db.flush()
    return p


# --- personalisation (no database) ----------------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [("ayesha", "Ayesha"), ("MARY-ANNE", "Mary-Anne"), ("McDonald", "McDonald"), ("  bilal  khan", "Bilal"), (None, "there"), ("   ", "there")])
def test_first_name_is_capitalised_or_replaced(raw, expected):
    assert r.first_name(raw) == expected


def test_prices_look_like_rs_3_500():
    assert r.price(3500) == "Rs. 3,500" and r.price(1234567) == "Rs. 1,234,567" and r.price(99.5) == "Rs. 99.50"
    assert r.price(None) is None and r.price("") is None


def test_description_is_cut_to_a_short_text_at_a_word():
    out = r.short("word " * 100, 40)
    assert len(out) <= 44 and out.endswith("...") and "wor..." not in out


@pytest.mark.parametrize("key", list(r.TEMPLATES))
def test_every_template_renders_with_sample_data_and_has_no_gaps(key):
    subject, html, text = r.render(key, r.sample_data(key))
    for out in (subject, html, text):
        assert "None" not in out and "{{" not in out and "{%" not in out
    assert "Ayesha" in subject and "<html" in html and "max-width:600px" in html
    assert text.strip() and "<" not in text


@pytest.mark.parametrize("key", list(r.TEMPLATES))
def test_every_template_survives_almost_no_data(key):
    subject, html, text = r.render(key, {})
    assert "Hi there" in html and "Hi there" in text and "None" not in html + text and "undefined" not in html


def test_the_discount_block_and_subject_only_appear_with_a_code():
    plain = r.render("winback", {**r.sample_data("winback"), "discount_code": None, "discount_value": None})
    assert plain[0] == "We miss you, Ayesha!" and "COMEBACK10" not in plain[1]
    coded = r.render("winback", r.sample_data("winback"))
    assert coded[0] == "Ayesha, here's 10% off, just for you" and "COMEBACK10" in coded[1] and "10% off your next order" in coded[2]


def test_new_product_subject_depends_on_the_customer_buying_before():
    data = r.sample_data("new_product")
    assert r.render("new_product", data)[0] == "Ayesha, you'll love our new Weekender Duffel"
    assert r.render("new_product", {**data, "same_category": False})[0] == "Ayesha, something new just arrived at Sample Store"


def test_html_is_escaped_so_a_product_name_cannot_inject_markup():
    html = r.render("new_product", {**r.sample_data("new_product"), "product_name": "<script>x</script>"})[1]
    assert "<script>x" not in html and "&lt;script&gt;" in html


def test_unusable_image_and_links_are_dropped():
    assert r.clean_url("javascript:alert(1)") is None and r.clean_url("data:text/html,x") is None and r.clean_url("https://a.test/x.png")
    assert r.clean_color("red; background:url(x)") == r.DEFAULT_COLOR and r.clean_color("#112233") == "#112233"


# --- COD confirmation ----------------------------------------------------------------------------------------------------


def test_a_cod_order_gets_one_email_and_waits_as_pending(db_session):
    customer = person(db_session, consented=False)                       # a transactional email needs no marketing consent
    o = order(db_session, customer)
    row = svc.send_cod_email(db_session, conf(), o, now=NOW)
    assert row.status == "pending" and row.sent_at == NOW
    log = db_session.query(EmailLog).one()
    assert log.kind == "cod" and log.status == "mock" and "please confirm your order" in log.subject and log.subject.startswith("Ayesha, ")
    assert svc.send_cod_email(db_session, conf(), o, now=NOW).sent_at == NOW
    assert db_session.query(EmailLog).count() == 1                       # asking again sends nothing


def test_prepaid_orders_and_customers_without_email_get_nothing(db_session):
    assert svc.send_cod_email(db_session, conf(), order(db_session, person(db_session), payment="prepaid")) is None
    nobody = person(db_session)
    nobody.email = None
    assert svc.send_cod_email(db_session, conf(), order(db_session, nobody)) is None
    assert db_session.query(EmailLog).count() == 0


def test_the_cod_email_contains_the_order_and_signed_links(db_session):
    customer = person(db_session)
    product(db_session, name="Test Shoes", price=3500)
    o = order(db_session, customer, products="Test Shoes")
    mail = svc.build_cod(db_session, conf(), o, customer, reminder=False)
    assert "Rs. 3,500" in mail.html and "Lahore" in mail.html and "Test Shoes" in mail.html and "https://img.test/a.png" in mail.html
    assert "/api/v1/email/cod/" in mail.html and "Confirm My Order" in mail.html and "Cancel Order" in mail.html and "Unsubscribe" not in mail.html


def test_tokens_cannot_be_forged_changed_or_used_after_they_expire():
    s = conf()
    token = svc.make_cod_token(s, 42, "confirm", NOW)
    assert svc.read_cod_token(s, token, NOW) == (42, "confirm")
    assert svc.read_cod_token(s, token, NOW + timedelta(days=svc.COD_LINK_DAYS + 1)) is None
    assert svc.read_cod_token(conf(messaging_secret="y" * 32), token, NOW) is None
    assert svc.read_cod_token(s, token[:-3] + "abc", NOW) is None and svc.read_cod_token(s, "garbage", NOW) is None
    assert svc.read_cod_token(s, svc.make_cod_token(s, 43, "cancel", NOW), NOW) == (43, "cancel")


def test_opening_the_link_changes_nothing_and_the_button_does(db_client, db_session):
    customer = person(db_session)
    o = order(db_session, customer)
    svc.send_cod_email(db_session, conf(), o, now=NOW)
    from app.core.config import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: conf()
    url = "/api/v1/email/cod/" + svc.make_cod_token(conf(), o.id, "confirm")
    shown = db_client.get(url)
    assert shown.status_code == 200 and "Yes, confirm my order" in shown.text and "Rs. 3,500" in shown.text
    assert svc.cod_email_for(db_session, o.id).status == "pending"       # a mail app previewing the link must not confirm
    done = db_client.post(url, headers={"origin": "http://api.test"})    # the page posts from the API's own address
    assert done.status_code == 200 and "is confirmed" in done.text
    assert svc.cod_email_for(db_session, o.id).status == "confirmed"
    again = db_client.get("/api/v1/email/cod/" + svc.make_cod_token(conf(), o.id, "cancel"))
    assert "Yes, cancel" not in again.text and "is confirmed" in again.text            # the first answer stands


def test_cancelling_works_and_a_bad_link_shows_an_error_page(db_client, db_session):
    from app.core.config import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: conf()
    o = order(db_session, person(db_session))
    out = db_client.post("/api/v1/email/cod/" + svc.make_cod_token(conf(), o.id, "cancel"))
    assert "has been cancelled" in out.text and svc.cod_email_for(db_session, o.id).status == "cancelled"
    bad = db_client.get("/api/v1/email/cod/not-a-real-token")
    assert bad.status_code == 400 and "not valid" in bad.text


def test_a_reminder_is_sent_once_after_24_hours_to_unanswered_orders_only(db_session):
    s = conf()
    waiting, answered, fresh = (order(db_session, person(db_session)) for _ in range(3))
    for o in (waiting, answered):
        svc.send_cod_email(db_session, s, o, now=NOW - timedelta(hours=30))
    svc.send_cod_email(db_session, s, fresh, now=NOW - timedelta(hours=2))
    svc.answer_cod(db_session, answered.id, "confirm", NOW)
    assert svc.send_due_reminders(db_session, s, NOW) == {"reminders": 1}
    assert svc.send_due_reminders(db_session, s, NOW) == {"reminders": 0}
    subjects = [e.subject for e in db_session.query(EmailLog).filter(EmailLog.kind == "cod_reminder")]
    assert len(subjects) == 1 and subjects[0].startswith("Reminder: your order #")


# --- win-back ------------------------------------------------------------------------------------------------------------


def test_customers_are_marked_at_risk_after_60_days_and_lost_after_180(db_session):
    fresh, risky, gone = person(db_session), person(db_session), person(db_session)
    order(db_session, fresh, days_ago=59), order(db_session, risky, days_ago=60), order(db_session, gone, days_ago=180)
    order(db_session, gone, days_ago=400)
    assert svc.refresh_lifecycle(db_session, NOW.date()) == {"active": 1, "at_risk": 1, "lost": 1}
    assert (fresh.lifecycle, risky.lifecycle, gone.lifecycle) == ("active", "at_risk", "lost")


def test_winback_goes_to_at_risk_and_lost_with_consent_and_never_twice_in_30_days(db_session):
    s = conf()
    risky, gone, active, stranger = person(db_session), person(db_session), person(db_session), person(db_session, consented=False)
    order(db_session, risky, days_ago=70), order(db_session, gone, days_ago=250), order(db_session, active, days_ago=5), order(db_session, stranger, days_ago=90)
    first = svc.send_winback(db_session, s, "welcome10", "10%", NOW)
    assert (first.sent, first.skipped) == (2, {"no consent or unsubscribed": 1})
    logs = db_session.query(EmailLog).filter(EmailLog.kind == "winback").all()
    assert {e.customer_id for e in logs} == {risky.id, gone.id} and all("10% off" in e.subject for e in logs)
    again = svc.send_winback(db_session, s, None, None, NOW + timedelta(days=10))
    assert again.sent == 0 and again.skipped["sent in the last 30 days"] == 2
    later = svc.send_winback(db_session, s, None, None, NOW + timedelta(days=31))
    assert later.sent == 2 and db_session.query(EmailLog).filter(EmailLog.subject.like("We miss you%")).count() == 2


def test_winback_has_an_unsubscribe_link_recommendations_and_last_product(db_session):
    s = conf()
    c = person(db_session, first="SANA")
    order(db_session, c, days_ago=90, products="Old Sandals", category="Shoes")
    product(db_session, name="Test Boots", category="Shoes"), product(db_session, name="Test Hat", category="Hats")
    mail = svc.build_winback(db_session, s, c, None, None, NOW.date())
    assert "/api/v1/unsubscribe?token=" in mail.html and mail.headers["List-Unsubscribe"].startswith("<http://api.test/api/v1/unsubscribe")
    assert "Old Sandals" in mail.html and "90 days" in mail.html and "Test Boots" in mail.html and "Hi Sana" in mail.html
    assert mail.html.index("Test Boots") < mail.html.index("Test Hat")           # the category they bought from comes first


def test_marketing_is_refused_without_an_unsubscribe_setup(db_session):
    with pytest.raises(ApiError) as e:
        svc.send_winback(db_session, conf(messaging_secret=None), None, None, NOW)
    assert e.value.code == "unsubscribe_not_configured"


def test_a_bad_discount_code_is_refused():
    with pytest.raises(ApiError):
        svc.clean_discount("<b>x</b>", "10%")
    assert svc.clean_discount(" save10 ", " 10% ") == ("SAVE10", "10%") and svc.clean_discount("", "10%") == (None, None)


def test_unsubscribing_stops_all_future_marketing(db_client, db_session):
    from app.core.config import get_settings
    from app.main import app
    from app.services.messaging.tokens import make_unsubscribe_token

    s = conf()
    app.dependency_overrides[get_settings] = lambda: s
    c = person(db_session)
    order(db_session, c, days_ago=90)
    assert db_client.get(f"/api/v1/unsubscribe?token={make_unsubscribe_token(s, c.id, 'email')}").status_code == 200
    assert svc.send_winback(db_session, s, None, None, NOW).sent == 0


# --- the daily limit -----------------------------------------------------------------------------------------------------


def test_marketing_stops_at_the_cap_but_cod_still_goes_out(db_session):
    s = conf()
    c = person(db_session)
    order(db_session, c, days_ago=90)
    for i in range(svc.MARKETING_CAP):
        db_session.add(EmailLog(to_email="x@testcustomer.test", kind="cod", subject="s", status="sent", created_at=NOW))
    db_session.flush()
    blocked = svc.send_winback(db_session, s, None, None, NOW)
    assert blocked.sent == 0 and "daily email limit" in blocked.message
    assert svc.send_cod_email(db_session, s, order(db_session, person(db_session)), now=NOW) is not None
    assert svc.sent_today(db_session, NOW) == svc.MARKETING_CAP + 1


def test_nothing_is_sent_once_the_hard_limit_is_reached(db_session):
    for i in range(svc.DAILY_LIMIT):
        db_session.add(EmailLog(to_email="x@testcustomer.test", kind="cod", subject="s", status="sent", created_at=NOW))
    db_session.flush()
    with pytest.raises(ApiError) as e:
        svc.send_cod_email(db_session, conf(), order(db_session, person(db_session)), now=NOW)
    assert e.value.code == "daily_limit"


def test_a_failed_send_is_logged_as_failed_and_does_not_count(db_session, monkeypatch):
    def refuse(*a, **k):
        raise OSError("down")

    monkeypatch.setattr(svc, "_brevo_send", refuse)
    s = conf(brevo_api_key="k" * 20)
    with pytest.raises(ApiError):
        svc.send_cod_email(db_session, s, order(db_session, person(db_session)), now=NOW)
    assert db_session.query(EmailLog).one().status == "failed" and svc.sent_today(db_session, NOW) == 0


def test_with_a_key_the_email_goes_through_brevo_with_the_shop_as_sender(db_session, monkeypatch):
    seen = []
    monkeypatch.setattr(svc, "_brevo_send", lambda settings, to, subject, html, text, headers, reply_to: seen.append((to, subject, bool(html), bool(text), reply_to)))
    c = person(db_session)
    svc.send_cod_email(db_session, conf(brevo_api_key="k" * 20), order(db_session, c), now=NOW)
    assert seen == [(c.email, seen[0][1], True, True, "shop@example.com")] and db_session.query(EmailLog).one().status == "sent"


# --- new product ---------------------------------------------------------------------------------------------------------


def test_announcement_goes_to_same_category_buyers_first_then_the_rest_once(db_session):
    s = conf()
    shoe, bag, out = person(db_session, first="zed"), person(db_session, first="amir"), person(db_session, consented=False)
    order(db_session, bag, category="Bags", days_ago=3), order(db_session, shoe, category="Shoes", days_ago=3), order(db_session, out, category="Shoes")
    ann = svc.create_announcement(db_session, name="Trail Runner", category="Shoes", price=Decimal(7500), description="Light and grippy. " * 20, image_url="https://img.test/t.png", product_url="https://shop.test/trail")
    assert ann.status == "draft" and db_session.query(EmailLog).count() == 0     # a draft sends nothing
    result = svc.send_announcement(db_session, s, ann, NOW)
    assert (result.sent, result.remaining) == (2, 0) and ann.status == "sent" and ann.sent_count == 2
    logs = db_session.query(EmailLog).filter(EmailLog.kind == "new_product").order_by(EmailLog.id).all()
    assert [e.customer_id for e in logs] == [shoe.id, bag.id]
    assert logs[0].subject == "Zed, you'll love our new Trail Runner" and logs[1].subject == "Amir, something new just arrived at Test Shop"
    assert svc.send_announcement(db_session, s, ann, NOW).sent == 0


def test_announcement_sends_in_batches_when_there_are_many(db_session):
    s = conf()
    for _ in range(5):
        person(db_session)
    ann = svc.create_announcement(db_session, name="Trail Runner", category=None, price=None, description=None, image_url=None, product_url=None)
    first = svc.send_announcement(db_session, s, ann, NOW, limit=3)
    assert (first.sent, first.remaining, ann.status) == (3, 2, "draft")
    assert svc.send_announcement(db_session, s, ann, NOW, limit=3).sent == 2 and ann.status == "sent"


def test_a_product_without_image_price_or_description_still_makes_a_clean_email(db_session):
    ann = svc.create_announcement(db_session, name="Plain Mug", category=None, price=None, description=None, image_url="javascript:x", product_url=None)
    mail = svc.build_announcement(db_session, conf(), ann, person(db_session), False, "http://api.test/u")
    assert "Plain Mug" in mail.html and "<img src=\"javascript" not in mail.html and "None" not in mail.html + mail.text and "Rs." not in mail.html


def test_a_shopify_product_also_makes_a_draft_email(db_session):
    from app.services import shopify_hooks

    out = shopify_hooks.handle(db_session, conf(shopify_shop_domain="demo.myshopify.com"), "products/create",
                               {"id": 9001, "title": "Linen Shirt", "product_type": "Shirts", "handle": "linen-shirt", "body_html": "<p>Cool</p>", "image": {"src": "https://img.test/s.png"}, "variants": [{"price": "3200.00"}]})
    assert out["product"] == "Linen Shirt"
    p = db_session.query(CatalogProduct).filter_by(external_id="9001").one()
    assert (p.image_url, p.product_url) == ("https://img.test/s.png", "https://demo.myshopify.com/products/linen-shirt")
    assert db_session.query(EmailAnnouncement).filter_by(product_id=p.id, status="draft").count() == 1


def test_a_new_shopify_cod_order_sends_the_email_without_failing_the_order(db_session):
    from app.services import shopify_hooks

    payload = {"id": 777, "name": "#1777", "email": "buyer@testcustomer.test", "total_price": "3500.00", "gateway": "Cash on Delivery", "payment_gateway_names": ["Cash on Delivery"],
               "customer": {"id": 5, "first_name": "bilal", "last_name": "khan", "email": "buyer@testcustomer.test"}, "shipping_address": {"city": "Karachi", "first_name": "bilal"},
               "line_items": [{"title": "Linen Shirt", "quantity": 1}]}
    shopify_hooks.handle(db_session, conf(), "orders/create", payload, NOW)
    o = db_session.query(Order).filter_by(external_id="SHOPIFY-777").one()
    if o.payment_type == "cod":
        assert db_session.query(CodEmail).filter_by(order_id=o.id).one().status == "pending"


# --- test mode and the page's data ---------------------------------------------------------------------------------------


def test_sample_data_can_be_loaded_twice_and_covers_every_case(db_session):
    s = conf()
    svc.load_sample_data(db_session, s, NOW.date())
    svc.load_sample_data(db_session, s, NOW.date())
    assert db_session.query(Customer).filter(Customer.external_id.like("MOCK-%")).count() == 5
    assert svc.refresh_lifecycle(db_session, NOW.date()) == {"active": 1, "at_risk": 2, "lost": 2}
    assert db_session.query(Customer).filter_by(external_id="MOCK-C1").one().email == "shop+mock1@example.com"
    cod = db_session.query(Order).filter_by(external_id="MOCK-O1").one()
    assert svc.send_cod_email(db_session, s, cod, now=NOW).status == "pending"


def test_test_emails_send_one_of_every_template_to_the_sender(db_session):
    mails = svc.send_test_emails(conf(), db_session)
    assert len(mails) == len(r.TEMPLATES) and {m.to for m in mails} == {"shop@example.com"} and all(m.subject.startswith("[Test] ") for m in mails)
    with pytest.raises(ApiError):
        svc.send_test_emails(conf(sender_email=None))


def test_the_dashboard_api(db_client, db_session):
    from app.core.config import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: conf()
    assert db_client.post("/api/v1/email-auto/mock/load").status_code == 200
    page = db_client.get("/api/v1/email-auto/overview").json()
    assert page["sentToday"] == 1 and page["cod"][0]["status"] == "pending" and page["dailyLimit"] == 300 and page["testMode"] is True and page["lifecycle"]["lost"] == 2
    cod = db_client.post(f"/api/v1/email-auto/cod/{db_session.query(Order).filter_by(external_id='MOCK-O1').one().id}/send")
    assert cod.status_code == 200 and cod.json()["status"] == "pending"
    assert db_client.get("/api/v1/email-auto/overview").json()["cod"][0]["status"] == "pending"
    sent = db_client.post("/api/v1/email-auto/winback/send", json={"discountCode": "back10", "discountValue": "10%"}).json()
    assert sent["sent"] == 4 and sent["testMode"] is True
    assert len(db_client.get("/api/v1/email-auto/previews").json()) == 4
    made = db_client.post("/api/v1/email-auto/announcements", json={"name": "Trail Runner", "category": "Shoes", "price": 7500}).json()
    preview = db_client.get(f"/api/v1/email-auto/announcements/{made['id']}/preview").json()
    assert "Trail Runner" in preview["html"] and preview["audience"]["sameCategory"] + preview["audience"]["others"] == 5
    assert db_client.post(f"/api/v1/email-auto/announcements/{made['id']}/send").json()["sent"] == 5
    assert db_client.put("/api/v1/email-auto/settings", json={"brandColor": "red"}).status_code == 422
    assert db_client.put("/api/v1/email-auto/settings", json={"storeName": "Zed Store", "brandColor": "#aa3300", "logoUrl": "https://img.test/logo.png"}).json()["effective"]["storeName"] == "Zed Store"
    assert "#aa3300" in db_client.get("/api/v1/email-auto/previews").json()[0]["html"]
