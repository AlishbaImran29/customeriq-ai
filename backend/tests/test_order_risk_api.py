"""GET /api/v1/order-risk: the page's data, the trust rule at the API level, and sign-in."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import ProgrammingError

from app.main import app
from app.models import Customer, OrderRiskRun
from app.services import order_risk_service
from tests.conftest import requires_database
from tests.test_order_risk_model import make_orders


@pytest.fixture(autouse=True)
def fresh_cache():
    order_risk_service.clear_cache()
    yield
    order_risk_service.clear_cache()


def use_orders(monkeypatch, orders):
    monkeypatch.setattr(order_risk_service, "load_order_inputs", lambda db: orders)


@requires_database
def test_available_model_returns_recent_orders_with_levels_reasons_and_savings(db_client, monkeypatch):
    use_orders(monkeypatch, make_orders(signal=True))
    body = db_client.get("/api/v1/order-risk").json()

    assert body["model"]["status"] == "available" and body["model"]["reason"] is None
    assert body["model"]["modelScore"] > body["model"]["baselineScore"]
    assert body["model"]["lowBelow"] == 0.2 and body["model"]["highAbove"] == 0.5
    assert body["model"]["labelSource"] == "proxy: cancellations"
    assert body["meta"]["source"] == "live" and body["windowDays"] == 30

    assert sum(body["levelCounts"].values()) == body["windowOrders"] > 0
    rank = {"High": 0, "Medium": 1, "Low": 2}
    levels = [o["level"] for o in body["orders"]]
    assert levels == sorted(levels, key=rank.get)                      # the risky ones come first
    for o in body["orders"]:
        assert 0.0 <= o["probability"] <= 1.0 and o["action"]
        assert len(o["reasons"]) <= 3
        for r in o["reasons"]:
            assert r["text"] == r["template"].format(**r["params"])

    for key in ("savingsHigh", "savingsMediumHigh"):
        s = body[key]
        assert s["flaggedReturned"] + s["falseAlarms"] == s["flaggedOrders"]
        assert s["flaggedReturned"] <= s["totalReturned"] <= s["testOrders"]
    assert body["savingsHigh"]["flaggedLevels"] == ["High"]
    assert body["savingsMediumHigh"]["flaggedOrders"] >= body["savingsHigh"]["flaggedOrders"]


@requires_database
def test_limit_cuts_the_table_and_says_so(db_client, monkeypatch):
    use_orders(monkeypatch, make_orders(signal=True))
    body = db_client.get("/api/v1/order-risk?limit=5").json()
    assert len(body["orders"]) == 5 and body["truncated"] is True
    assert body["windowOrders"] > 5                                     # the counts still cover everything
    assert db_client.get("/api/v1/order-risk?limit=0").status_code == 422


@requires_database
def test_when_the_model_is_not_trusted_there_are_no_orders_levels_or_savings(db_client, monkeypatch):
    use_orders(monkeypatch, make_orders(signal=False))
    body = db_client.get("/api/v1/order-risk").json()
    model = body["model"]
    assert model["status"] == "unavailable" and "baseline" in model["reason"]
    assert model["modelScore"] is not None and model["baselineScore"] is not None   # the evidence is still shown
    assert body["orders"] == [] and body["savingsHigh"] is None and body["savingsMediumHigh"] is None
    assert body["levelCounts"] == {"Low": 0, "Medium": 0, "High": 0}


@requires_database
def test_no_orders_at_all(db_client):
    body = db_client.get("/api/v1/order-risk").json()
    assert body["model"]["status"] == "unavailable" and "No orders" in body["model"]["reason"]
    assert body["orders"] == [] and body["meta"]["asOf"] is None


@requires_database
def test_customer_name_and_a_readable_phone_become_a_whatsapp_number(db_client, db_session, monkeypatch):
    orders = make_orders(signal=True)
    latest = max(orders, key=lambda o: o.order_date)
    db_session.add(Customer(external_id=latest.customer_id, email="a@example.com", first_name="Ayesha", phone="0300 1234567"))
    db_session.commit()
    use_orders(monkeypatch, orders)

    rows = [o for o in db_client.get("/api/v1/order-risk?limit=1000").json()["orders"] if o["customerId"] == latest.customer_id]
    assert rows and all(r["customerName"] == "Ayesha" and r["whatsappPhone"] == "923001234567" for r in rows)
    others = [o for o in db_client.get("/api/v1/order-risk?limit=1000").json()["orders"] if o["customerId"] != latest.customer_id]
    assert others and all(r["whatsappPhone"] is None for r in others)            # no phone in the data


@requires_database
def test_each_retraining_is_saved_once_and_repeat_requests_use_the_cache(db_client, db_session, monkeypatch):
    use_orders(monkeypatch, make_orders(signal=True))
    db_client.get("/api/v1/order-risk")
    db_client.get("/api/v1/order-risk")
    assert db_session.scalar(select(func.count()).select_from(OrderRiskRun)) == 1
    run = db_session.scalar(select(OrderRiskRun))
    assert run.decision == "available" and run.model_score > run.baseline_score

    use_orders(monkeypatch, make_orders(signal=False))                           # the data changed
    db_client.get("/api/v1/order-risk")
    assert db_session.scalar(select(func.count()).select_from(OrderRiskRun)) == 2


@pytest.mark.real_auth
def test_sign_in_is_required():
    assert TestClient(app).get("/api/v1/order-risk").status_code == 401


@requires_database
def test_an_out_of_date_database_gives_a_clear_message_not_a_generic_error(db_client, monkeypatch):
    def missing_column(db):
        raise ProgrammingError("SELECT ordered_at", {}, Exception("column orders.ordered_at does not exist"))

    monkeypatch.setattr(order_risk_service, "load_order_inputs", missing_column)
    response = db_client.get("/api/v1/order-risk")
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "database_out_of_date" and "migrate_remote.py" in error["message"]
