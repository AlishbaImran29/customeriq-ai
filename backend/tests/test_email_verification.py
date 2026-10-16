"""Sign-up with an emailed code (the email itself is captured, never sent)."""

import smtplib
import ssl
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core import security
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.main import app
from app.models import User
from app.services import auth as svc
from app.services import mailer
from tests.conftest import requires_database

pytestmark = [pytest.mark.real_auth, requires_database]

PASSWORD = "blue tractor sings loudly"
MAIL = dict(smtp_host="smtp.test", smtp_user="owner@test.example", smtp_password="app-password")


@pytest.fixture(autouse=True)
def fast_hashing(monkeypatch):
    monkeypatch.setattr(security, "SCRYPT_N", 2**10)
    monkeypatch.setattr(security, "SCRYPT_P", 1)


@pytest.fixture
def outbox(monkeypatch):
    """Replaces the real sender; every code that would have been emailed lands here."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        mailer, "send_verification_code", lambda settings, to, name, code, minutes: sent.append((to, code))
    )
    return sent


@pytest.fixture
def mail_client(db_client):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **MAIL)
    return TestClient(app)


def setup_owner(client, outbox, email="owner@example.com"):
    response = client.post("/api/v1/auth/setup", json={"name": "Owner", "email": email, "password": PASSWORD})
    assert response.status_code == 202, response.text
    verified = client.post("/api/v1/auth/verify", json={"email": email, "code": outbox[-1][1]})
    assert verified.status_code == 200, verified.text
    return TestClient(app)  # a fresh browser with no cookie


def sign_up(client, email="new@example.com", password=PASSWORD):
    return client.post("/api/v1/auth/signup", json={"name": "New", "email": email, "password": password})


def wrong_code(real: str) -> str:
    return "000000" if real != "000000" else "111111"


def test_signup_is_closed_without_email_set_up(db_client):
    status = db_client.get("/api/v1/auth/status").json()
    assert status["verificationEnabled"] is False and status["signupOpen"] is False
    assert sign_up(db_client).json()["error"]["code"] == "signup_closed"


def test_owner_must_confirm_their_email_before_signing_in(mail_client, outbox):
    status = mail_client.get("/api/v1/auth/status").json()
    assert status["setupRequired"] is True and status["verificationEnabled"] is True and status["signupOpen"] is False

    response = mail_client.post(
        "/api/v1/auth/setup", json={"name": "Owner", "email": "Owner@Example.com", "password": PASSWORD}
    )
    assert response.status_code == 202
    assert response.json() == {"verificationRequired": True, "email": "owner@example.com"}
    assert "set-cookie" not in response.headers  # not signed in yet
    assert mail_client.get("/api/v1/auth/me").status_code == 401
    assert mail_client.get("/api/v1/customers").status_code == 401
    assert [to for to, _ in outbox] == ["owner@example.com"] and len(outbox[0][1]) == 6

    # The right password still cannot sign in until the email is confirmed.
    blocked = mail_client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": PASSWORD})
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "email_not_verified"

    verified = mail_client.post("/api/v1/auth/verify", json={"email": "owner@example.com", "code": outbox[0][1]})
    assert verified.status_code == 200 and "ciq_session" in verified.headers["set-cookie"]
    assert mail_client.get("/api/v1/auth/me").json()["email"] == "owner@example.com"
    status = TestClient(app).get("/api/v1/auth/status").json()
    assert status["setupRequired"] is False and status["signupOpen"] is True


def test_code_is_stored_only_as_a_hash(mail_client, outbox, db_session):
    mail_client.post("/api/v1/auth/setup", json={"name": "Owner", "email": "owner@example.com", "password": PASSWORD})
    user = db_session.query(User).one()
    assert user.verify_code_hash and outbox[0][1] not in user.verify_code_hash and len(user.verify_code_hash) == 64


def test_owner_can_start_over_after_mistyping_their_email(mail_client, outbox):
    first = mail_client.post("/api/v1/auth/setup", json={"name": "A", "email": "typo@exmaple.com", "password": PASSWORD})
    assert first.status_code == 202
    again = mail_client.post("/api/v1/auth/setup", json={"name": "A", "email": "right@example.com", "password": PASSWORD})
    assert again.status_code == 202 and outbox[-1][0] == "right@example.com"


def test_anyone_can_sign_up_and_must_confirm_before_seeing_data(mail_client, outbox):
    owner = setup_owner(mail_client, outbox)
    assert owner.get("/api/v1/auth/status").json()["signupOpen"] is True

    browser = TestClient(app)
    response = sign_up(browser)
    assert response.status_code == 202 and response.json()["email"] == "new@example.com"
    assert browser.get("/api/v1/customers").status_code == 401
    code = outbox[-1][1]

    bad = browser.post("/api/v1/auth/verify", json={"email": "new@example.com", "code": wrong_code(code)})
    assert bad.json()["error"]["code"] == "invalid_code"
    ok = browser.post("/api/v1/auth/verify", json={"email": "new@example.com", "code": code})
    assert ok.status_code == 200 and browser.get("/api/v1/customers").status_code == 200
    # The code works once only.
    assert browser.post("/api/v1/auth/verify", json={"email": "new@example.com", "code": code}).status_code == 400


def test_confirmed_emails_cannot_be_signed_up_again(mail_client, outbox):
    setup_owner(mail_client, outbox)
    taken = sign_up(TestClient(app), email="owner@example.com")
    assert taken.status_code == 409 and taken.json()["error"]["code"] == "email_taken"


def test_signup_can_be_turned_off(db_client, outbox):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, allow_signup=False, **MAIL)
    client = TestClient(app)
    setup_owner(client, outbox)
    assert client.get("/api/v1/auth/status").json()["signupOpen"] is False
    assert sign_up(client).json()["error"]["code"] == "signup_closed"


def test_wrong_codes_are_limited_even_if_the_right_one_comes_later(mail_client, outbox):
    setup_owner(mail_client, outbox)
    browser = TestClient(app)
    sign_up(browser)
    good = outbox[-1][1]
    for _ in range(svc.MAX_CODE_ATTEMPTS):
        attempt = browser.post("/api/v1/auth/verify", json={"email": "new@example.com", "code": wrong_code(good)})
        assert attempt.status_code == 400
    locked = browser.post("/api/v1/auth/verify", json={"email": "new@example.com", "code": good})
    assert locked.status_code == 429 and locked.json()["error"]["code"] == "too_many_attempts"


def test_expired_code_is_refused(mail_client, outbox, db_session):
    setup_owner(mail_client, outbox)
    browser = TestClient(app)
    sign_up(browser)
    user = db_session.query(User).filter_by(email="new@example.com").one()
    user.verify_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.flush()
    expired = browser.post("/api/v1/auth/verify", json={"email": "new@example.com", "code": outbox[-1][1]})
    assert expired.status_code == 400 and expired.json()["error"]["code"] == "code_expired"


def test_resend_is_rate_limited_and_never_reveals_who_has_an_account(mail_client, outbox, monkeypatch):
    setup_owner(mail_client, outbox)
    browser = TestClient(app)
    sign_up(browser)
    count = len(outbox)
    # Within the cooldown: same friendly answer, but no second email.
    assert browser.post("/api/v1/auth/resend", json={"email": "new@example.com"}).status_code == 202
    assert len(outbox) == count
    # Unknown and already-confirmed addresses get the same answer and no email.
    assert browser.post("/api/v1/auth/resend", json={"email": "nobody@example.com"}).status_code == 202
    assert browser.post("/api/v1/auth/resend", json={"email": "owner@example.com"}).status_code == 202
    assert len(outbox) == count
    # After the cooldown a new code is sent, and it replaces the old one.
    monkeypatch.setattr(svc, "RESEND_COOLDOWN_SECONDS", 0)
    old = outbox[-1][1]
    assert browser.post("/api/v1/auth/resend", json={"email": "new@example.com"}).status_code == 202
    assert len(outbox) == count + 1
    fresh = outbox[-1][1]
    if fresh != old:
        assert browser.post("/api/v1/auth/verify", json={"email": "new@example.com", "code": old}).status_code == 400
    assert browser.post("/api/v1/auth/verify", json={"email": "new@example.com", "code": fresh}).status_code == 200


def test_hourly_cap_on_codes(mail_client, outbox, monkeypatch):
    setup_owner(mail_client, outbox)
    monkeypatch.setattr(svc, "RESEND_COOLDOWN_SECONDS", 0)
    browser = TestClient(app)
    for _ in range(svc.MAX_CODES_PER_HOUR):
        assert sign_up(browser).status_code == 202
    capped = sign_up(browser)
    assert capped.status_code == 429 and capped.json()["error"]["code"] == "too_many_codes"


def test_logging_in_with_an_unconfirmed_account_sends_a_code(mail_client, outbox, monkeypatch):
    setup_owner(mail_client, outbox)
    monkeypatch.setattr(svc, "RESEND_COOLDOWN_SECONDS", 0)
    browser = TestClient(app)
    sign_up(browser)
    before = len(outbox)
    blocked = browser.post("/api/v1/auth/login", json={"email": "new@example.com", "password": PASSWORD})
    assert blocked.status_code == 403 and blocked.json()["error"]["details"] == {"email": "new@example.com"}
    assert len(outbox) == before + 1
    # A wrong password reveals nothing about confirmation.
    wrong = browser.post("/api/v1/auth/login", json={"email": "new@example.com", "password": "wrong password here"})
    assert wrong.json()["error"]["code"] == "invalid_credentials"


# --- the mailer itself ---------------------------------------------------------------------


class FakeSMTP:
    instances: list["FakeSMTP"] = []
    fail = False

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.actions = host, port, []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.actions.append("starttls")

    def login(self, user, password):
        if FakeSMTP.fail:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials app-password")
        self.actions.append(("login", user, password))

    def send_message(self, message):
        body = message.get_body(("plain",)).get_content()
        self.actions.append(("send", message["To"], message["Subject"], body))


def test_mailer_sends_over_starttls_with_the_code_in_the_message(monkeypatch):
    FakeSMTP.instances.clear()
    FakeSMTP.fail = False
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    name = "Ali" + chr(13) + chr(10) + "Bcc: x@y.z"
    mailer.send_verification_code(Settings(_env_file=None, **MAIL), "person@example.com", name, "123456", 15)
    (smtp,) = FakeSMTP.instances
    assert smtp.host == "smtp.test" and smtp.port == 587
    assert smtp.actions[0] == "starttls" and smtp.actions[1] == ("login", "owner@test.example", "app-password")
    _, to, subject, body = smtp.actions[2]
    assert to == "person@example.com" and "123456" in subject and "123456" in body
    assert "Ali Bcc: x@y.z" in body  # line breaks in the name are flattened, so no new line or header starts


def test_mail_failure_gives_a_friendly_error_without_leaking_details(monkeypatch):
    FakeSMTP.fail = True
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    with pytest.raises(ApiError) as caught:
        mailer.send_verification_code(Settings(_env_file=None, **MAIL), "person@example.com", "Ali", "123456", 15)
    assert caught.value.status_code == 503 and caught.value.code == "email_send_failed"
    assert caught.value.details == {"reason": "login_refused", "kind": "SMTPAuthenticationError", "errno": None}  # never the server's own text
    assert "app-password" not in caught.value.message and "535" not in caught.value.message
    FakeSMTP.fail = False


def test_connection_problems_get_distinct_reasons():
    import errno
    import socket

    assert mailer._failure_reason(socket.gaierror(-2, "Name or service not known")) == "host_not_found"
    assert mailer._failure_reason(ConnectionRefusedError()) == "port_closed"
    assert mailer._failure_reason(OSError(errno.ENETUNREACH, "Network is unreachable")) == "network_blocked"
    assert mailer._failure_reason(TimeoutError()) == "timeout"
    assert mailer._failure_reason(smtplib.SMTPAuthenticationError(535, b"x")) == "login_refused"
    assert mailer._failure_reason(ssl.SSLError("handshake")) == "tls_failed"
    assert mailer._failure_reason(OSError("something else")) == "unreachable"


# --- Brevo (HTTPS) ---------------------------------------------------------------------------

BREVO = dict(brevo_api_key="xkeysib-secret-value", mail_from="sender@example.com")


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b"{}"


def test_brevo_alone_counts_as_email_being_set_up():
    assert Settings(_env_file=None, **BREVO).email_configured is True
    assert Settings(_env_file=None, brevo_api_key="k").email_configured is False  # needs a sender address
    assert Settings(_env_file=None, mail_from="a@b.co").email_configured is False  # needs the key
    assert Settings(_env_file=None, **BREVO).signup_open is True


def test_brevo_request_has_the_key_in_a_header_and_the_code_in_the_body(monkeypatch):
    import json
    import urllib.request

    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"], seen["headers"], seen["body"] = request.full_url, dict(request.header_items()), json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    mailer.send_verification_code(Settings(_env_file=None, **BREVO), "person@example.com", "Ali", "654321", 15)
    assert seen["url"] == "https://api.brevo.com/v3/smtp/email"
    assert seen["headers"]["Api-key"] == "xkeysib-secret-value"
    assert seen["body"]["sender"]["email"] == "sender@example.com"
    assert seen["body"]["to"] == [{"email": "person@example.com"}]
    assert "654321" in seen["body"]["subject"] and "654321" in seen["body"]["textContent"] and "654321" in seen["body"]["htmlContent"]
    assert "xkeysib" not in json.dumps(seen["body"])  # the key never goes into the message


@pytest.mark.parametrize("status, reason", [(401, "login_refused"), (400, "sender_refused"), (402, "provider_limit"), (500, "smtp_error")])
def test_brevo_errors_become_safe_labels(monkeypatch, status, reason):
    import urllib.error
    import urllib.request

    def fail(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, status, "secret server text xkeysib-secret-value", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(ApiError) as caught:
        mailer.send_verification_code(Settings(_env_file=None, **BREVO), "person@example.com", "Ali", "123456", 15)
    assert caught.value.code == "email_send_failed"
    assert caught.value.details == {"reason": reason, "kind": "HTTPError", "errno": status}
    assert "xkeysib" not in caught.value.message and "secret server text" not in caught.value.message
