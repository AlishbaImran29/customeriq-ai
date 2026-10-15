"""The cleanup script removes only SYN- rows (run inside a rolled-back transaction)."""

import importlib.util
from pathlib import Path

from sqlalchemy import select

from app.models import Customer, ImportJob, Order
from tests.conftest import requires_database

_spec = importlib.util.spec_from_file_location(
    "delete_synthetic_data",
    Path(__file__).resolve().parents[1] / "scripts" / "delete_synthetic_data.py",
)
cleanup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cleanup)


def upload(client, name: str, rows: list[str]) -> None:
    content = "customer_id,email,order_id,order_date,order_value\n" + "\n".join(rows)
    response = client.post("/api/v1/imports", files={"file": (name, content.encode(), "text/csv")})
    assert response.status_code == 201, response.text


@requires_database
def test_only_synthetic_rows_are_deleted(db_client, db_session):
    upload(db_client, "demo_orders_synthetic.csv", [
        "SYN-C0001,a@example.com,SYN-O1,2026-01-01,10",
        "SYN-C0002,b@example.com,SYN-O2,2026-01-02,20",
    ])
    upload(db_client, "real_orders.csv", ["REAL-1,real@example.com,ORD-9,2026-01-03,30"])

    assert cleanup.counts(db_session) == {
        "orders": 2, "customers": 2, "import_jobs": 1, "real_customers_kept": 1,
    }
    cleanup.delete_synthetic(db_session)
    db_session.flush()

    assert db_session.scalars(select(Customer.external_id)).all() == ["REAL-1"]
    assert db_session.scalars(select(Order.external_id)).all() == ["ORD-9"]
    assert db_session.scalars(select(ImportJob.filename)).all() == ["real_orders.csv"]
