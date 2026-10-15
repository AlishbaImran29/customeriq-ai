"""End-to-end import API tests against PostgreSQL (rolled back after each test)."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models import Customer, ImportJob, Order
from tests.conftest import requires_database

HEADER = "customer_id,email,order_id,order_date,order_value,first_name,engagement"


def upload(client, content: str | bytes, filename: str = "orders.csv"):
    data = content.encode() if isinstance(content, str) else content
    return client.post("/api/v1/imports", files={"file": (filename, data, "text/csv")})


# --- request-level errors (no database needed) ------------------------------

@pytest.fixture
def client():
    return TestClient(app)


def test_missing_file_field_is_validation_error(client):
    response = client.post("/api/v1/imports")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_wrong_extension_is_415(client):
    response = upload(client, "hello", "notes.txt")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file_type"


def test_file_too_large_is_413(client, monkeypatch):
    monkeypatch.setattr("app.api.v1.imports.MAX_FILE_BYTES", 10)
    response = upload(client, HEADER + "\n" + "x" * 50)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


# --- database-backed --------------------------------------------------------

@requires_database
def test_partial_import_saves_valid_rows_and_reports_bad_ones(db_client, db_session):
    response = upload(
        db_client,
        "\n".join([
            HEADER,
            "C1,amelia@example.com,O1,2026-01-05,100.00,Amelia,80",
            "C1,amelia@example.com,O2,2026-02-05,50.25,,",
            "C2,noah@example.com,O3,2026-02-10,abc,,",
        ]),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert (body["rowsReceived"], body["rowsImported"], body["rowsUpdated"], body["rowsRejected"]) == (3, 2, 0, 1)
    assert body["errors"] == [{"row": 4, "column": "order_value", "message": "Not a number. Use digits only, e.g. 142.50."}]
    assert body["errorsTruncated"] is False

    assert db_session.scalar(select(func.count()).select_from(Customer)) >= 1
    o2 = db_session.scalar(select(Order).where(Order.external_id == "O2"))
    assert o2.order_value == Decimal("50.25") and o2.engagement_score is None


@requires_database
def test_reupload_updates_existing_orders(db_client, db_session):
    upload(db_client, f"{HEADER}\nC9,old@example.com,O9,2026-01-01,10,Maya,40")
    response = upload(db_client, f"{HEADER}\nC9,new@example.com,O9,2026-01-02,25.5,,")
    body = response.json()
    assert (body["rowsImported"], body["rowsUpdated"]) == (0, 1)

    order = db_session.scalar(select(Order).where(Order.external_id == "O9"))
    db_session.refresh(order)
    assert order.order_value == Decimal("25.50")
    assert order.engagement_score == Decimal("40.00")  # blank keeps previous value
    customer = db_session.scalar(select(Customer).where(Customer.external_id == "C9"))
    db_session.refresh(customer)
    assert customer.email == "new@example.com" and customer.first_name == "Maya"


@requires_database
def test_missing_columns_saves_nothing(db_client, db_session):
    before = db_session.scalar(select(func.count()).select_from(ImportJob))
    response = upload(db_client, "customer_id,email\nC1,a@example.com")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "missing_columns"
    assert db_session.scalar(select(func.count()).select_from(ImportJob)) == before


@requires_database
def test_get_and_list_imports(db_client):
    created = upload(db_client, f"{HEADER}\nC5,e@example.com,O5,2026-01-01,1,,").json()
    one = db_client.get(f"/api/v1/imports/{created['id']}")
    assert one.status_code == 200 and one.json()["id"] == created["id"]
    listed = db_client.get("/api/v1/imports?limit=5").json()
    assert listed[0]["id"] == created["id"] and "errors" not in listed[0]


@requires_database
def test_unknown_import_is_404(db_client):
    response = db_client.get("/api/v1/imports/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "import_not_found"
