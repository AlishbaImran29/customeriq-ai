"""Sign-in flow against PostgreSQL (rolled back after each test)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import require_user
from app.core import security
from app.core.config import Settings, get_settings
from app.main import app, create_app
from app.models import User, UserSession
from app.services import auth as auth_service
from tests.conftest import requires_database

pytestmark = [pytest.mark.real_auth, requires_database]

PASSWORD = "blue tractor sings loudly"
NEW_PASSWORD = "seven green umbrellas dance"


@pytest.fixture(autouse=True)
def fast_hashing(monkeypatch):
    monkeypatch.setattr(security, "SCRYPT_N", 2**10)
    monkeypatch.setattr(security, "SCRYPT_P", 1)


def sign_up(client, email="owner@example.com", password=PASSWORD, **extra):
    return client.post("/api/v1/auth/setup", json={"name": "Alishba", "email": email, "password": password, **extra})


def login(client, email="owner@example.com", password=PASSWORD, remember=False):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password, "remember": remember})


# --- before and after the first account ---------------------------------------------------

def test_data_endpoints_need_sign_in_but_health_does_not(db_client):
    for path in ("/api/v1/customers", "/api/v1/dashboard/overview", "/api/v1/imports",
                 "/api/v1/assistant/status", "/api/v1/auth/me"):
        response = db_client.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "not_signed_in"
    assert db_client.post("/api/v1/assistant/chat", json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 401
    assert db_client.post("/api/v1/imports", files={"file": ("a.csv", b"x", "text/csv")}).status_code == 401
    assert db_client.get("/api/v1/health").status_code == 200


def test_status_before_and_after_setup(db_client):
    assert db_client.get("/api/v1/auth/status").json() == {
        "setupRequired": True, "setupCodeRequired": False, "authenticated": False, "user": None,
    }
    assert sign_up(db_client).status_code == 201
    body = db_client.get("/api/v1/auth/status").json()
    assert body["setupRequired"] is False and body["authenticated"] is True
    assert body["user"]["email"] == "owner@example.com" and body["user"]["name"] == "Alishba"


def test_setup_signs_you_in_and_sets_a_safe_cookie(db_client):
    response = sign_up(db_client)
    assert response.status_code == 201
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie
    assert db_client.get("/api/v1/auth/me").json()["email"] == "owner@example.com"
    assert db_client.get("/api/v1/customers").status_code == 200


def test_setup_works_only_once(db_client):
    assert sign_up(db_client).status_code == 201
    again = sign_up(TestClient(app), email="intruder@example.com")
    assert again.status_code == 409 and again.json()["error"]["code"] == "setup_done"


# --- sign in / out ----------------------------------------------------------------------------

def test_login_logout_cycle(db_client, db_session):
    sign_up(db_client)
    other = TestClient(app)
    assert other.get("/api/v1/auth/me").status_code == 401
    assert login(other, email="  OWNER@Example.com ").status_code == 200  # email is case-insensitive
    assert other.get("/api/v1/customers").status_code == 200
    assert other.post("/api/v1/auth/logout").status_code == 204
    assert other.get("/api/v1/auth/me").status_code == 401
    assert db_session.scalar(select(func.count()).select_from(UserSession)) == 1  # only the setup session left


def test_wrong_credentials_get_one_generic_message(db_client):
    sign_up(db_client)
    wrong_password = login(TestClient(app), password="not the right one at all")
    unknown_email = login(TestClient(app), email="nobody@example.com")
    for response in (wrong_password, unknown_email):
        assert response.status_code == 401
        assert response.json()["error"] == {
            "code": "invalid_credentials", "message": "That email or password is not correct.", "details": None,
        }


def test_remember_me_controls_cookie_lifetime(db_client):
    sign_up(db_client)
    remembered = login(TestClient(app), remember=True).headers["set-cookie"].lower()
    assert f"max-age={30 * 24 * 3600}" in remembered
    browser_session = login(TestClient(app), remember=False).headers["set-cookie"].lower()
    assert "max-age" not in browser_session and "expires" not in browser_session


def test_lockout_after_repeated_failures(db_client):
    sign_up(db_client)
    client = TestClient(app)
    for _ in range(auth_service.MAX_FAILED_LOGINS):
        assert login(client, password="wrong password here").status_code == 401
    locked = login(client)  # even the right password is refused while locked
    assert locked.status_code == 429
    error = locked.json()["error"]
    assert error["code"] == "too_many_attempts" and "wait about" in error["message"]
    assert error["details"]["retryAfterSeconds"] > 0


def test_successful_login_resets_the_failure_count(db_client):
    sign_up(db_client)
    client = TestClient(app)
    for _ in range(auth_service.MAX_FAILED_LOGINS - 1):
        login(client, password="wrong password here")
    assert login(client).status_code == 200
    for _ in range(auth_service.MAX_FAILED_LOGINS - 1):
        assert login(client, password="wrong password here").status_code == 401
    assert login(client).status_code == 200  # still not locked


# --- validation with friendly messages -----------------------------------------------------------

@pytest.mark.parametrize("payload, code, field", [
    ({"email": "not-an-email", "password": PASSWORD}, "invalid_email", "email"),
    ({"email": "a@example.com", "password": "short"}, "weak_password", "password"),
    ({"email": "a@example.com", "password": "1234567890"}, "weak_password", "password"),
    ({"email": "alishba@example.com", "password": "alishba-is-great-123"}, "weak_password", "password"),
])
def test_setup_validation_errors_name_the_field(db_client, payload, code, field):
    response = db_client.post("/api/v1/auth/setup", json={"name": "A", **payload})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == code and error["details"] == {"field": field}
    assert error["message"].endswith(".")  # a readable sentence, not a code


def test_setup_with_missing_fields_is_a_validation_error(db_client):
    assert db_client.post("/api/v1/auth/setup", json={"email": "a@example.com"}).status_code == 422


def test_name_defaults_to_the_email_name(db_client):
    body = db_client.post("/api/v1/auth/setup", json={"email": "maya@example.com", "password": PASSWORD}).json()
    assert body["name"] == "maya"


# --- setup code for public deployments -----------------------------------------------------------------

def test_setup_code_protects_the_first_account(db_client):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, setup_code="open-sesame")
    client = TestClient(app)
    assert client.get("/api/v1/auth/status").json()["setupCodeRequired"] is True
    missing = sign_up(client)
    assert missing.status_code == 403 and missing.json()["error"]["code"] == "invalid_setup_code"
    assert sign_up(client, setupCode="wrong").status_code == 403
    assert sign_up(client, setupCode="open-sesame").status_code == 201
    assert TestClient(app).get("/api/v1/auth/status").json()["setupCodeRequired"] is False


# --- change password --------------------------------------------------------------------------------------

def test_change_password_signs_out_other_browsers_only(db_client):
    sign_up(db_client)
    other = TestClient(app)
    login(other)
    change = db_client.post("/api/v1/auth/change-password",
                            json={"currentPassword": PASSWORD, "newPassword": NEW_PASSWORD})
    assert change.status_code == 204
    assert db_client.get("/api/v1/auth/me").status_code == 200   # this browser stays signed in
    assert other.get("/api/v1/auth/me").status_code == 401       # the other one is signed out
    assert login(TestClient(app), password=PASSWORD).status_code == 401
    assert login(TestClient(app), password=NEW_PASSWORD).status_code == 200


@pytest.mark.parametrize("payload, status, code", [
    ({"currentPassword": "wrong wrong wrong", "newPassword": NEW_PASSWORD}, 400, "wrong_password"),
    ({"currentPassword": PASSWORD, "newPassword": "short"}, 422, "weak_password"),
    ({"currentPassword": PASSWORD, "newPassword": PASSWORD}, 422, "same_password"),
])
def test_change_password_errors(db_client, payload, status, code):
    sign_up(db_client)
    response = db_client.post("/api/v1/auth/change-password", json=payload)
    assert response.status_code == status and response.json()["error"]["code"] == code


def test_change_password_requires_sign_in(db_client):
    response = db_client.post("/api/v1/auth/change-password",
                              json={"currentPassword": PASSWORD, "newPassword": NEW_PASSWORD})
    assert response.status_code == 401


# --- what is stored ---------------------------------------------------------------------------------------------

def test_database_holds_only_hashes(db_client, db_session):
    sign_up(db_client)
    token = db_client.cookies.get("ciq_session")
    user = db_session.scalars(select(User)).one()
    assert user.password_hash.startswith("scrypt$") and PASSWORD not in user.password_hash
    stored = db_session.scalars(select(UserSession)).one()
    assert stored.token_hash == security.hash_token(token) and token not in stored.token_hash


def test_expired_session_is_rejected(db_client, db_session):
    sign_up(db_client)
    session = db_session.scalars(select(UserSession)).one()
    session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.flush()
    assert db_client.get("/api/v1/auth/me").status_code == 401


def test_deactivated_users_are_locked_out(db_client, db_session):
    sign_up(db_client)
    db_session.scalars(select(User)).one().is_active = False
    db_session.flush()
    assert db_client.get("/api/v1/auth/me").status_code == 401           # existing session stops working
    assert login(TestClient(app)).status_code == 401                      # and so does signing in


def test_a_garbage_cookie_is_just_signed_out(db_client):
    db_client.cookies.set("ciq_session", "definitely-not-a-real-token")
    assert db_client.get("/api/v1/auth/me").status_code == 401
    assert db_client.get("/api/v1/auth/status").json()["authenticated"] is False


# --- other websites and production mode -------------------------------------------------------------------------------

def test_writes_from_other_websites_are_refused(db_client):
    sign_up(db_client)
    evil = {"Origin": "https://evil.example"}
    blocked = db_client.post("/api/v1/auth/logout", headers=evil)
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "forbidden_origin"
    assert db_client.get("/api/v1/auth/me", headers=evil).status_code == 200   # reading is not a write
    assert db_client.post("/api/v1/auth/logout", headers={"Origin": "http://localhost:3001"}).status_code == 204


def test_production_mode_uses_secure_cookies_and_hides_docs(db_client, monkeypatch):
    production = Settings(_env_file=None, app_env="production")
    app.dependency_overrides[get_settings] = lambda: production
    client = TestClient(app, base_url="https://testserver")
    assert "secure" in sign_up(client).headers["set-cookie"].lower()
    assert client.get("/api/v1/auth/me").status_code == 200

    monkeypatch.setattr("app.main.get_settings", lambda: production)
    locked_down = TestClient(create_app())
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert locked_down.get(path).status_code == 404
    assert TestClient(app).get("/docs").status_code == 200  # development keeps the docs


def test_real_guard_is_used_when_not_overridden():
    # Sanity check for this test module: no stand-in user is active.
    assert require_user not in app.dependency_overrides
