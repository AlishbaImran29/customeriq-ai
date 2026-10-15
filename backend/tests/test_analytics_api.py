"""Analytics endpoints against PostgreSQL (data rolled back after each test)."""

from datetime import date, timedelta

import pytest

from tests.conftest import requires_database

ENDPOINTS = [
    "/api/v1/dashboard/overview",
    "/api/v1/customers",
    "/api/v1/segments",
    "/api/v1/predictions/churn",
    "/api/v1/predictions/clv",
    "/api/v1/customers/health",
    "/api/v1/revenue/intelligence",
    "/api/v1/recommendations",
]


def import_customers(client, count: int) -> None:
    today = date(2026, 10, 1)
    lines = ["customer_id,email,order_id,order_date,order_value,engagement"]
    for i in range(count):
        for k in range(1 + i % 4):
            day = today - timedelta(days=i * 9 + k * 30)
            engagement = "" if i % 3 == 0 else str(40 + i % 50)
            lines.append(f"T{i},t{i}@example.com,T{i}-{k},{day},{20 + i * 3}.00,{engagement}")
    response = client.post(
        "/api/v1/imports", files={"file": ("t.csv", "\n".join(lines).encode(), "text/csv")}
    )
    assert response.status_code == 201, response.text


@requires_database
@pytest.mark.parametrize("path", ENDPOINTS)
def test_endpoints_with_no_data_return_empty_state(db_client, path):
    response = db_client.get(path)
    assert response.status_code == 200, response.text
    meta = response.json()["meta"]
    assert meta["asOf"] is None and meta["customerCount"] == 0 and meta["source"] == "live"


@requires_database
def test_overview_with_data(db_client):
    import_customers(db_client, 30)
    body = db_client.get("/api/v1/dashboard/overview").json()
    assert body["meta"]["segmented"] is True
    assert body["kpis"]["totalCustomers"] == 30
    assert body["kpis"]["churnRisk"] is None  # churn needs a trained model; this data is too small
    details = body["growthScoreDetails"]
    assert details is not None and body["kpis"]["growthScore"] == details["score"]  # 4 inputs measurable here
    assert 0 <= details["score"] <= 100 and {c["key"] for c in details["components"]} >= {"health", "retention"}
    unavailable = {u["field"] for u in body["meta"]["unavailable"]}
    assert {"churnRisk", "revenueForecast"} <= unavailable and "growthScore" not in unavailable
    assert body["executiveSummary"]["method"] == "rules"
    assert sum(s["customers"] for s in body["segments"]) == 30
    assert all(s["avgPredictedClv"] is None for s in body["segments"])


@requires_database
def test_customers_have_no_predictions_and_flag_missing_engagement(db_client):
    import_customers(db_client, 25)
    body = db_client.get("/api/v1/customers?limit=10").json()
    assert body["total"] == 25 and len(body["customers"]) == 10
    for c in body["customers"]:
        assert c["predictedClv"] is None and c["churnProbability"] is None
        assert c["riskLevel"] in {"Low", "Medium", "High", "Critical"}
        assert (c["healthFactors"]["engagement"] is None) == c["engagementMissing"]
    assert any(c["engagementMissing"] for c in db_client.get("/api/v1/customers").json()["customers"])


@requires_database
def test_small_dataset_is_not_segmented(db_client):
    import_customers(db_client, 5)
    body = db_client.get("/api/v1/segments").json()
    assert body["segments"] == [] and body["meta"]["segmented"] is False
    assert any(u["field"] == "segments" for u in body["meta"]["unavailable"])


@requires_database
def test_limit_is_validated(db_client):
    response = db_client.get("/api/v1/customers?limit=0")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
