"""Abandoned carts: record Shopify checkouts, remind once or twice, never without consent, stop when they buy.
Everything is made up (marked TEST); nothing is really sent."""

from datetime import datetime, timedelta, timezone

from app.core.config import Settings
from app.models import Customer, Message
from app.models.abandoned_cart import AbandonedCart
from app.services import carts
from app.services.messaging import defaults
from tests.test_order_status import make_customer, make_order, make_template, opt_in

NOW = datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc)                      # 12:00 in Pakistan: not quiet hours


def settings() -> Settings:
    return Settings(_env_file=None, messaging_dry_run=True)


def checkout(cid="CK1", phone="+923001234567", when=NOW, **extra):
    return {"id": cid, "phone": phone, "email": "", "updated_at": when.isoformat(), "total_price": "3500.00", "currency": "PKR",
            "abandoned_checkout_url": f"https://shop.example/checkouts/{cid}", "line_items": [{"title": "Test shoes", "quantity": 2}], **extra}


def known_customer(db, consent=True):
    customer = make_customer(db)
    if consent:
        opt_in(db, customer)
    return customer


def templates(db):
    for n in (1, 2):
        make_template(db, f"cart_reminder_{n}", body="Hi {{first_name}}, finish {{items}} ({{amount}}): {{checkout_url}}", category="marketing")


def test_a_checkout_is_saved_and_updates_restart_the_clock(db_session):
    customer = known_customer(db_session)
    cart = carts.record_checkout(db_session, checkout(), NOW)
    assert (cart.status, cart.customer_id, cart.items, float(cart.total)) == ("open", customer.id, "Test shoes x2", 3500.0)
    carts.record_checkout(db_session, checkout(when=NOW + timedelta(minutes=30)), NOW + timedelta(minutes=30))
    assert db_session.query(AbandonedCart).count() == 1 and cart.checkout_updated_at == NOW + timedelta(minutes=30)


def test_a_shopper_we_do_not_know_is_recorded_but_never_messaged(db_session):
    templates(db_session)
    cart = carts.record_checkout(db_session, checkout(phone="+923009990000"), NOW)
    assert cart.status == "no_contact"
    assert carts.run_due(db_session, settings(), NOW + timedelta(days=1))["reminders"] == 0
    assert db_session.query(Message).count() == 0


def test_reminder_one_waits_for_the_delay_and_reminder_two_for_its_own(db_session):
    known_customer(db_session)
    templates(db_session)
    cart = carts.record_checkout(db_session, checkout(), NOW)
    assert carts.run_due(db_session, settings(), NOW + timedelta(minutes=30))["reminders"] == 0              # 60 minutes by default
    assert carts.run_due(db_session, settings(), NOW + timedelta(minutes=61))["reminders"] == 1
    assert carts.run_due(db_session, settings(), NOW + timedelta(minutes=62))["reminders"] == 0              # not twice in a row
    assert carts.run_due(db_session, settings(), NOW + timedelta(hours=10))["reminders"] == 0
    assert carts.run_due(db_session, settings(), NOW + timedelta(hours=26))["reminders"] == 1                # 24 hours after the first
    assert carts.run_due(db_session, settings(), NOW + timedelta(hours=60))["reminders"] == 0                # never a third
    assert cart.reminders_sent == 2 and db_session.query(Message).count() == 2
    first = db_session.query(Message).order_by(Message.id).first()
    assert "https://shop.example/checkouts/CK1" in first.rendered_text and "Test shoes x2" in first.rendered_text


def test_the_delays_are_settings_and_the_second_reminder_can_be_switched_off(db_session):
    from app.services.messaging.settings_store import get_row

    row = get_row(db_session)
    row.cart_first_minutes, row.cart_second_hours = 15, 0
    known_customer(db_session)
    templates(db_session)
    carts.record_checkout(db_session, checkout(), NOW)
    assert carts.run_due(db_session, settings(), NOW + timedelta(minutes=16))["reminders"] == 1
    assert carts.run_due(db_session, settings(), NOW + timedelta(days=3))["reminders"] == 0                  # 0 = no second reminder


def test_no_consent_means_no_message_and_the_cart_is_parked(db_session):
    known_customer(db_session, consent=False)
    templates(db_session)
    cart = carts.record_checkout(db_session, checkout(), NOW)
    counts = carts.run_due(db_session, settings(), NOW + timedelta(hours=2))
    assert cart.status == "no_contact" and counts["no_contact"] == 1 and db_session.query(Message).count() == 0


def test_nothing_is_sent_until_a_template_is_approved(db_session):
    known_customer(db_session)
    make_template(db_session, "cart_reminder_1", approved=False, category="marketing", body="Hi {{first_name}} {{checkout_url}}")
    cart = carts.record_checkout(db_session, checkout(), NOW)
    assert carts.run_due(db_session, settings(), NOW + timedelta(hours=2))["reminders"] == 0
    assert cart.status == "open" and cart.reminders_sent == 0                                                # still waiting, not lost


def test_buying_stops_the_reminders(db_session):
    customer = known_customer(db_session)
    templates(db_session)
    carts.record_checkout(db_session, checkout(), NOW)
    order = make_order(db_session, customer)
    assert carts.mark_recovered(db_session, order, "CK1", NOW + timedelta(minutes=10)) == 1
    assert carts.run_due(db_session, settings(), NOW + timedelta(hours=3))["reminders"] == 0
    assert db_session.query(AbandonedCart).one().status == "recovered"


def test_an_order_by_the_same_customer_recovers_the_cart_even_without_the_checkout_id(db_session):
    customer = known_customer(db_session)
    carts.record_checkout(db_session, checkout(), NOW)
    assert carts.mark_recovered(db_session, make_order(db_session, customer), None, NOW) == 1


def test_a_completed_checkout_is_recovered_and_old_carts_expire(db_session):
    known_customer(db_session)
    done = carts.record_checkout(db_session, checkout("CK2", completed_at=NOW.isoformat()), NOW)
    assert done.status == "recovered"
    carts.record_checkout(db_session, checkout("CK3", when=NOW - timedelta(days=9)), NOW)
    assert carts.run_due(db_session, settings(), NOW)["expired"] == 1


def test_reminder_templates_are_marketing_and_have_the_checkout_link(db_session):
    rows = defaults.default_templates(["carts"])
    assert len(rows) == 8 and {r["category"] for r in rows} == {"marketing"} and all("{{checkout_url}}" in r["body"] for r in rows)


def test_shopify_checkout_and_order_webhooks_drive_it(db_session):
    from app.services import shopify_hooks

    known_customer(db_session)
    shopify_hooks.handle(db_session, settings(), "checkouts/create", checkout("CK9"), NOW)
    assert db_session.query(AbandonedCart).one().status == "open"
    order = {"id": 777, "name": "#1001", "checkout_id": "CK9", "total_price": "3500.00", "phone": "+923001234567", "created_at": NOW.isoformat(),
             "line_items": [{"title": "Test shoes", "quantity": 2}], "customer": {"id": 5, "phone": "+923001234567"}}
    shopify_hooks.handle(db_session, settings(), "orders/create", order, NOW)
    assert db_session.query(AbandonedCart).one().status == "recovered"
    assert db_session.query(Customer).count() == 1


def test_api_lists_carts_and_hides_a_rate_until_there_are_enough(db_client, db_session):
    known_customer(db_session)
    carts.record_checkout(db_session, checkout(), NOW)
    db_session.commit()
    rows = db_client.get("/api/v1/carts").json()
    assert rows[0]["items"] == "Test shoes x2" and rows[0]["status"] == "open"
    summary = db_client.get("/api/v1/carts/summary").json()
    assert summary["counts"]["open"] == 1 and summary["recoveryRate"] is None and "not the effect" in summary["note"]
