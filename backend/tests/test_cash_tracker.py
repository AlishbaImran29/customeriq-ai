"""The Cash Tracker: FIFO matching, payment import, totals and buckets. All amounts and names are invented."""

import io
from datetime import date, timedelta
from decimal import Decimal
from itertools import count

import pytest

from app.models import CourierPayment, Shipment
from app.models.shipment import SOURCE_DEMO
from app.services.cash_matching import PAID, PARTLY, PENDING, Parcel, Payment, match
from app.services.cash_tracker import compute_tracker, pending_list
from app.services.import_files import parse_file
from app.services.payment_import import import_payments, validate_payments

D = Decimal
DAY = date(2026, 3, 1)


def parcel(key, days_after, amount, courier="TESTCOURIER", ref=None):
    return Parcel(key=key, courier=courier, delivered_on=DAY + timedelta(days=days_after), amount=D(amount), order_ref=ref)


def pay(key, days_after, amount, courier="TESTCOURIER", refs=()):
    return Payment(key=key, courier=courier, paid_on=DAY + timedelta(days=days_after), amount=D(amount), order_refs=list(refs))


# --- FIFO rules (pure, no database) -------------------------------------------------------------


def test_payment_covers_the_oldest_parcels_first():
    parcels = [parcel(2, 5, 1000), parcel(1, 0, 1000), parcel(3, 9, 1000)]       # key 1 is the oldest
    match(parcels, [pay(1, 20, 1500)])
    by_key = {p.key: p for p in parcels}
    assert by_key[1].status == PAID and by_key[2].status == PARTLY and by_key[2].paid == D(500) and by_key[3].status == PENDING


def test_days_to_pay_is_the_payment_date_that_finished_the_parcel():
    parcels = [parcel(1, 0, 1000)]
    match(parcels, [pay(1, 4, 400), pay(2, 10, 600)])
    assert parcels[0].status == PAID and parcels[0].settled_on == DAY + timedelta(days=10) and parcels[0].days_to_pay == 10


def test_partly_paid_has_no_days_to_pay():
    parcels = [parcel(1, 0, 1000)]
    match(parcels, [pay(1, 4, 400)])
    assert parcels[0].status == PARTLY and parcels[0].days_to_pay is None and parcels[0].due == D(600)


def test_a_payment_cannot_pay_a_parcel_delivered_after_it():
    parcels = [parcel(1, 10, 1000)]
    credit = match(parcels, [pay(1, 5, 1000)])
    assert parcels[0].status == PENDING and credit == {"TESTCOURIER": D(1000)}


def test_extra_money_is_credit_not_lost():
    parcels = [parcel(1, 0, 1000)]
    assert match(parcels, [pay(1, 3, 1800)]) == {"TESTCOURIER": D(800)}


def test_named_orders_are_paid_before_older_ones():
    parcels = [parcel(1, 0, 1000, ref="OLD"), parcel(2, 5, 1000, ref="NEW")]
    match(parcels, [pay(1, 20, 1000, refs=["NEW"])])
    assert parcels[1].status == PAID and parcels[0].status == PENDING


def test_each_courier_is_matched_on_its_own():
    parcels = [parcel(1, 0, 1000, courier="AAA"), parcel(2, 0, 1000, courier="BBB")]
    match(parcels, [pay(1, 3, 1000, courier="BBB")])
    assert parcels[0].status == PENDING and parcels[1].status == PAID


def test_matching_twice_in_a_different_input_order_gives_the_same_result():
    a = [parcel(1, 0, 700), parcel(2, 3, 900), parcel(3, 6, 400)]
    b = [a[2], a[0], a[1]]
    payments = [pay(1, 8, 800), pay(2, 12, 600)]
    match(a, payments)
    b2 = [parcel(3, 6, 400), parcel(1, 0, 700), parcel(2, 3, 900)]
    match(b2, list(reversed(payments)))
    assert sorted((p.key, p.paid) for p in a) == sorted((p.key, p.paid) for p in b2)


# --- payment import ----------------------------------------------------------------------------


CSV = (
    "courier_name,payment_date,amount,reference,order_ids\n"
    "t.c.s,2026-03-10,\"12,500\",TEST-REF-1,\"A-1; A-2\"\n"
    "TCS,2026-03-12,500,,\n"
)


def validate(text):
    return validate_payments(parse_file(text.encode(), "csv"))


def test_valid_rows_get_standard_names_and_clean_order_lists():
    result = validate(CSV)
    assert result.errors == [] and [r.courier.name for r in result.rows] == ["TCS", "TCS"]
    assert result.rows[0].amount == D("12500.00") and result.rows[0].order_refs == "A-1,A-2"


def test_bad_rows_are_rejected_with_the_column_and_without_echoing_the_value():
    result = validate("courier_name,payment_date,amount\n,2026-03-10,5\nTCS,not-a-date,5\nTCS,2026-03-10,-5\nTCS,2026-03-10,0\n")
    assert result.rejected == 4
    assert {(e.row, e.column) for e in result.errors} == {(2, "courier_name"), (3, "payment_date"), (4, "amount"), (5, "amount")}
    assert "not-a-date" not in " ".join(e.message for e in result.errors)


def test_future_dates_are_rejected():
    future = (date.today() + timedelta(days=3)).isoformat()
    assert validate(f"courier_name,payment_date,amount\nTCS,{future},5\n").rejected == 1


def test_missing_required_column_is_an_error():
    from app.core.errors import ApiError

    with pytest.raises(ApiError):
        validate("courier_name,amount\nTCS,5\n")


def test_importing_the_same_file_twice_does_not_double_the_money(db_session):
    first = import_payments(db_session, CSV.encode(), "csv")
    second = import_payments(db_session, CSV.encode(), "csv")
    assert (first.created, first.updated, second.created, second.updated) == (2, 0, 0, 2)
    assert db_session.query(CourierPayment).count() == 2


def test_two_identical_rows_in_one_file_are_two_payments(db_session):
    text = "courier_name,payment_date,amount\nTCS,2026-03-10,500\nTCS,2026-03-10,500\n"
    assert import_payments(db_session, text.encode(), "csv").created == 2


# --- the tracker (database) --------------------------------------------------------------------

_ids = count(1)
AS_OF = date(2026, 4, 1)


def delivered(db, courier, delivered_on, cod, *, city="Testville", source="import"):
    db.add(Shipment(
        external_id=f"T-{next(_ids)}", courier=courier, city=city, booked_date=delivered_on - timedelta(days=3),
        closed_date=delivered_on, status="delivered", cod_amount=D(cod), source=source,
    ))
    db.flush()


def paid(db, courier, when, amount, *, source="import", refs=None):
    db.add(CourierPayment(external_id=f"P-{next(_ids)}", courier=courier, payment_date=when, amount=D(amount), source=source, order_refs=refs))
    db.flush()


def test_totals_and_the_per_courier_table(db_session):
    delivered(db_session, "TESTCOURIER", date(2026, 3, 1), 1000)
    delivered(db_session, "TESTCOURIER", date(2026, 3, 5), 2000)
    delivered(db_session, "TESTCOURIER", date(2026, 3, 28), 500)
    paid(db_session, "TESTCOURIER", date(2026, 3, 10), 1500)                 # covers #1 and half of #2
    t = compute_tracker(db_session, as_of=AS_OF)
    assert (t.delivered_cod, t.received, t.pending) == (D(3500), D(1500), D(2000))
    assert t.unpaid_parcels == 2 and t.oldest_pending_days == 27             # parcel #2, delivered 5 March
    c = t.couriers[0]
    assert (c.courier, c.unpaid_parcels, c.paid_parcels, c.pending) == ("TESTCOURIER", 2, 1, D(2000))
    assert c.average_days_to_pay is None and not c.enough and c.needed == 19   # one paid parcel is far below the minimum


def test_age_buckets_and_the_alert_threshold(db_session):
    delivered(db_session, "TESTCOURIER", AS_OF - timedelta(days=3), 100)     # 0-7
    delivered(db_session, "TESTCOURIER", AS_OF - timedelta(days=10), 200)    # 8-14
    delivered(db_session, "TESTCOURIER", AS_OF - timedelta(days=15), 300)    # 15+
    delivered(db_session, "TESTCOURIER", AS_OF - timedelta(days=40), 400)    # 15+
    t = compute_tracker(db_session, as_of=AS_OF)
    assert [(b.label, b.parcels, b.amount) for b in t.buckets] == [("0-7", 1, D(100)), ("8-14", 1, D(200)), ("15+", 2, D(700))]
    assert t.alert_days == 14 and t.alerts[0].overdue_parcels == 2 and t.alerts[0].overdue_amount == D(700)
    strict = compute_tracker(db_session, as_of=AS_OF, alert_days=5)
    assert strict.alerts[0].overdue_parcels == 3
    assert compute_tracker(db_session, as_of=AS_OF, alert_days=60).alerts == []


def test_average_days_to_pay_needs_enough_paid_parcels(db_session):
    for i in range(20):
        delivered(db_session, "BIGCOURIER", date(2026, 1, 1) + timedelta(days=i), 100)
        delivered(db_session, "SMALLCOURIER", date(2026, 1, 1) + timedelta(days=i), 100) if i < 19 else None
    paid(db_session, "BIGCOURIER", date(2026, 2, 1), 2000)
    paid(db_session, "SMALLCOURIER", date(2026, 2, 1), 1900)
    by_name = {c.courier: c for c in compute_tracker(db_session, as_of=AS_OF).couriers}
    assert by_name["BIGCOURIER"].enough and by_name["BIGCOURIER"].average_days_to_pay is not None
    assert by_name["SMALLCOURIER"].paid_parcels == 19 and by_name["SMALLCOURIER"].average_days_to_pay is None


def test_returned_and_unfinished_parcels_are_not_owed(db_session):
    for status in ("returned", "in_transit", "lost"):
        db_session.add(Shipment(external_id=f"T-{next(_ids)}", courier="TESTCOURIER", booked_date=DAY, closed_date=DAY if status == "returned" else None,
                                status=status, cod_amount=D(900), source="import"))
    delivered(db_session, "TESTCOURIER", DAY, 0)                              # delivered, but nothing to collect
    db_session.flush()
    assert compute_tracker(db_session, as_of=AS_OF).delivered_cod == D(0)


def test_real_data_hides_demo_data_and_demo_is_used_alone_when_nothing_is_real(db_session):
    delivered(db_session, "DEMOCOURIER", DAY, 5000, source=SOURCE_DEMO)
    paid(db_session, "DEMOCOURIER", DAY + timedelta(days=5), 1000, source=SOURCE_DEMO)
    assert compute_tracker(db_session, as_of=AS_OF).source_used == "demo"
    delivered(db_session, "TESTCOURIER", DAY, 700)
    t = compute_tracker(db_session, as_of=AS_OF)
    assert t.source_used == "real" and t.delivered_cod == D(700) and t.received == D(0) and t.demo_cod_parcels == 1


def test_pending_list_is_oldest_first_and_has_the_amount_still_owed(db_session):
    delivered(db_session, "TESTCOURIER", date(2026, 3, 5), 1000)
    delivered(db_session, "TESTCOURIER", date(2026, 3, 1), 1000)
    paid(db_session, "TESTCOURIER", date(2026, 3, 10), 400)
    rows = pending_list(db_session, as_of=AS_OF)
    assert [r.delivered_on for r in rows] == [date(2026, 3, 1), date(2026, 3, 5)]
    assert (rows[0].status, rows[0].still_owed, rows[1].status) == ("partly_paid", D(600), "pending")


def test_api_tracker_manual_payment_and_csv_import(db_client, db_session):
    delivered(db_session, "TCS", date(2026, 3, 1), 1000)
    body = db_client.post("/api/v1/cash/payments", json={"courierName": "t.c.s", "paymentDate": "2026-03-05", "amount": 400, "reference": "TEST-1"})
    assert body.status_code == 201 and body.json()["courier"] == "TCS"
    bad = db_client.post("/api/v1/cash/payments", json={"courierName": "TCS", "paymentDate": "2026-03-05", "amount": 0})
    assert bad.status_code == 422
    files = {"file": ("payments.csv", io.BytesIO(b"courier_name,payment_date,amount\nTCS,2026-03-06,100\n"), "text/csv")}
    assert db_client.post("/api/v1/cash/payments/import", files=files).json()["created"] == 1
    t = db_client.get("/api/v1/cash/tracker?alert_days=14").json()
    assert t["received"] == 500 and t["pending"] == 500 and t["minGroupCount"] == 20
    assert db_client.get("/api/v1/cash/pending").json()[0]["stillOwed"] == 500
    assert db_client.get("/api/v1/cash/tracker?alert_days=0").status_code == 422
