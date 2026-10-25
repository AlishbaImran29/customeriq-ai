"""Roles and the action log: the policy table, enforcement over HTTP for each role, what is logged, the last-owner rule."""

import uuid
from types import SimpleNamespace

import pytest

from app.api.deps import require_user
from app.core import permissions as perm
from app.main import app
from app.models import AuditLog, User


def as_role(role: str, email: str | None = None):
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=uuid.uuid4(), email=email or f"{role}@test.example", name=role.title(), role=role)


# --- the table itself (pure) -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,needed", [
    ("GET", "/api/v1/customers", "viewer"),
    ("GET", "/api/v1/messaging/settings", "viewer"),
    ("GET", "/api/v1/audit", "owner"),
    ("GET", "/api/v1/team/users", "owner"),
    ("GET", "/api/v1/customer-records/export.csv", "owner"),
    ("POST", "/api/v1/orders", "staff"),
    ("POST", "/api/v1/leads/5/move", "staff"),
    ("POST", "/api/v1/returns/5/approve", "staff"),
    ("POST", "/api/v1/inventory/items/5/adjust", "staff"),
    ("POST", "/api/v1/assistant/ask", "viewer"),
    ("POST", "/api/v1/workflows/test", "viewer"),
    ("PUT", "/api/v1/messaging/settings", "owner"),
    ("POST", "/api/v1/customer-records/anonymise", "owner"),
    ("POST", "/api/v1/customer-records/merge", "owner"),
    ("POST", "/api/v1/refunds/7/record", "owner"),
    ("POST", "/api/v1/workflows/3/enable", "owner"),
    ("PATCH", "/api/v1/team/users/abc", "owner"),
    ("DELETE", "/api/v1/campaigns/4", "owner"),
    ("DELETE", "/api/v1/anything/at/all", "owner"),
])
def test_the_minimum_role_for_a_request(method, path, needed):
    assert perm.minimum_role(method, path) == needed


def test_roles_are_ordered_and_an_unknown_role_gets_nothing():
    assert perm.allowed("owner", "DELETE", "/api/v1/x") and perm.allowed("staff", "POST", "/api/v1/orders") and not perm.allowed("staff", "DELETE", "/api/v1/x")
    assert perm.allowed("viewer", "GET", "/api/v1/customers") and not perm.allowed("viewer", "POST", "/api/v1/orders")
    assert not perm.allowed(None, "GET", "/api/v1/customers") and not perm.allowed("admin", "GET", "/api/v1/customers")


# --- over HTTP ----------------------------------------------------------------------------------------------------------------


def test_a_viewer_can_look_and_ask_but_not_change(db_client):
    as_role("viewer")
    assert db_client.get("/api/v1/leads").status_code == 200
    assert db_client.post("/api/v1/workflows/validate", json={"name": "x", "trigger": "order_created", "actions": []}).status_code == 200
    blocked = db_client.post("/api/v1/leads", json={"phone": "03001234567"})
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "forbidden" and "only look" in blocked.json()["error"]["message"]
    assert db_client.get("/api/v1/audit").status_code == 403


def test_staff_do_the_daily_work_but_not_settings_deletions_or_refund_payments(db_client):
    as_role("staff")
    assert db_client.post("/api/v1/leads", json={"phone": "03001234567"}).status_code == 201
    assert db_client.put("/api/v1/messaging/settings", json={"weeklyMarketingCap": 3}).status_code == 403
    assert db_client.post("/api/v1/customer-records/delete", json={"customerId": "x", "confirm": True}).status_code == 403
    assert db_client.post("/api/v1/customer-records/anonymise", json={"customerId": "x", "confirm": True}).status_code == 403
    assert db_client.post("/api/v1/refunds/1/record", json={"method": "bank"}).status_code == 403
    assert db_client.delete("/api/v1/workflows/1").status_code == 403
    assert db_client.get("/api/v1/customer-records/export.csv").status_code == 403
    assert db_client.get("/api/v1/team/users").status_code == 403
    assert "only the account owner" in db_client.get("/api/v1/audit").json()["error"]["message"].lower()


def test_the_owner_can_do_everything(db_client):
    as_role("owner")
    assert db_client.put("/api/v1/messaging/settings", json={"weeklyMarketingCap": 3}).status_code == 200
    assert db_client.get("/api/v1/team/users").status_code == 200 and db_client.get("/api/v1/audit").status_code == 200


def test_a_user_without_a_role_is_refused_everything(db_client):
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=uuid.uuid4(), email="norole@test.example", name="No Role")
    assert db_client.get("/api/v1/leads").status_code == 403


# --- the action log -----------------------------------------------------------------------------------------------------------------


def test_changes_and_refusals_are_logged_but_reading_is_not(db_client, db_session):
    as_role("staff", "staff.person@test.example")
    db_client.get("/api/v1/leads")
    created = db_client.post("/api/v1/leads", json={"name": "Test Secret Name", "phone": "03001234567"})
    db_client.post("/api/v1/refunds/9/record", json={"method": "JazzCash", "reference": "TX-SECRET"})
    rows = db_session.query(AuditLog).order_by(AuditLog.id).all()
    assert [(r.method, r.route, r.outcome) for r in rows] == [("POST", "/api/v1/leads", "allowed"), ("POST", "/api/v1/refunds/{refund_id}/record", "denied")]
    assert rows[0].actor_email == "staff.person@test.example" and rows[0].actor_role == "staff" and rows[1].detail == {"ids": {"refund_id": "9"}}
    logged = " ".join(str(r.detail) + r.route for r in rows)
    assert "Test Secret Name" not in logged and "TX-SECRET" not in logged and "03001234567" not in logged       # what was typed is never logged
    assert created.status_code == 201


def test_the_owner_reads_the_log_with_filters(db_client):
    as_role("staff", "someone@test.example")
    db_client.post("/api/v1/refunds/9/record", json={"method": "x"})
    db_client.post("/api/v1/leads", json={"phone": "03001234567"})
    as_role("owner")
    everything = db_client.get("/api/v1/audit").json()
    denied = db_client.get("/api/v1/audit?outcome=denied").json()
    mine = db_client.get("/api/v1/audit?actor=someone@test.example").json()
    assert len(everything) >= 2 and [r["route"] for r in denied] == ["/api/v1/refunds/{refund_id}/record"] and len(mine) == 2


# --- managing roles -----------------------------------------------------------------------------------------------------------


def make_user(db, email, role, active=True):
    from datetime import UTC, datetime

    user = User(email=email, name=email.split("@")[0], password_hash="x", role=role, is_active=active, email_verified_at=datetime.now(UTC))
    db.add(user)
    db.flush()
    return user


def test_the_owner_changes_roles_and_the_last_owner_is_protected(db_client, db_session):
    only_owner = make_user(db_session, "boss@test.example", "owner")
    worker = make_user(db_session, "worker@test.example", "viewer")
    db_session.commit()
    as_role("owner")
    listed = db_client.get("/api/v1/team/users").json()
    assert {m["email"]: m["role"] for m in listed} == {"boss@test.example": "owner", "worker@test.example": "viewer"}
    assert db_client.patch(f"/api/v1/team/users/{worker.id}", json={"role": "staff"}).json()["role"] == "staff"
    assert db_client.patch(f"/api/v1/team/users/{only_owner.id}", json={"role": "staff"}).status_code == 409           # nobody would be left in charge
    assert db_client.patch(f"/api/v1/team/users/{only_owner.id}", json={"isActive": False}).status_code == 409
    db_client.patch(f"/api/v1/team/users/{worker.id}", json={"role": "owner"})
    assert db_client.patch(f"/api/v1/team/users/{only_owner.id}", json={"role": "staff"}).status_code == 200            # now there is another owner
    assert db_client.patch(f"/api/v1/team/users/{uuid.uuid4()}", json={"role": "staff"}).status_code == 404
    assert db_client.patch(f"/api/v1/team/users/{worker.id}", json={"role": "boss"}).status_code == 422


@pytest.mark.real_auth
def test_the_first_account_is_the_owner_and_later_signups_are_viewers(db_client, db_session):
    from app.services import auth as svc

    first = db_client.post("/api/v1/auth/setup", json={"email": "first.owner@test.example", "name": "First", "password": "A-very-long-test-passphrase-1!"})
    assert first.status_code in (201, 202)                                                    # 202 = waiting for the emailed code
    assert svc.user_by_email(db_session, "first.owner@test.example").role == "owner"
    assert svc.create_user(db_session, email="second.person@test.example", name="Second", password="A-very-long-test-passphrase-2!").role == "viewer"
