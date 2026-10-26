"""Sign-in with Supabase Auth: the token check, the first owner, approval of new accounts, and the pages behind sign-in.
Supabase is replaced by a fake: no network call is made."""

import io
import json
import urllib.error
import uuid

import pytest

from app.core.config import get_settings
from app.main import app
from app.models import User
from app.services import auth as svc

pytestmark = pytest.mark.real_auth


@pytest.fixture(autouse=True)
def supabase_settings():
    app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(update={"supabase_url": "https://project.supabase.test", "supabase_anon_key": "anon-key", "owner_email": None})
    svc.reset_token_cache()
    yield
    svc.reset_token_cache()


class FakeSupabase:
    """Pretends to be Supabase's /auth/v1/user: a token is valid only if it is in `accounts`."""

    def __init__(self, monkeypatch):
        self.accounts: dict[str, dict] = {}
        self.calls = 0
        monkeypatch.setattr(svc.urllib.request, "urlopen", self.urlopen)

    def add(self, token: str, email: str, name: str | None = None) -> uuid.UUID:
        account_id = uuid.uuid4()
        self.accounts[token] = {"id": str(account_id), "email": email, "user_metadata": {"name": name} if name else {}}
        return account_id

    def urlopen(self, request, timeout):
        self.calls += 1
        assert request.full_url == "https://project.supabase.test/auth/v1/user" and request.headers["Apikey"] == "anon-key"
        token = request.headers["Authorization"].removeprefix("Bearer ")
        if token not in self.accounts:
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b"{}"))
        return io.BytesIO(json.dumps(self.accounts[token]).encode())


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def supabase(monkeypatch):
    return FakeSupabase(monkeypatch)


def test_pages_behind_sign_in_need_a_token(db_client, supabase):
    assert db_client.get("/api/v1/leads").status_code == 401
    assert db_client.get("/api/v1/leads", headers=auth("forged")).status_code == 401
    assert db_client.get("/api/v1/auth/me").status_code == 401
    assert db_client.get("/api/v1/leads", headers={"Authorization": "Basic abc"}).status_code == 401
    assert db_client.get("/api/v1/health").status_code == 200                                     # the health check stays public


def test_the_first_account_becomes_the_owner_and_can_see_data(db_client, db_session, supabase):
    supabase.add("tok-first", "First.Owner@Test.Example", "First Owner")
    me = db_client.get("/api/v1/auth/me", headers=auth("tok-first"))
    assert me.status_code == 200
    assert (me.json()["email"], me.json()["name"], me.json()["role"], me.json()["isActive"]) == ("first.owner@test.example", "First Owner", "owner", True)
    assert db_client.get("/api/v1/leads", headers=auth("tok-first")).status_code == 200
    assert db_session.query(User).count() == 1


def test_later_accounts_wait_for_approval_and_see_no_data(db_client, db_session, supabase):
    supabase.add("tok-owner", "owner@test.example")
    supabase.add("tok-newcomer", "newcomer@test.example")
    db_client.get("/api/v1/auth/me", headers=auth("tok-owner"))
    me = db_client.get("/api/v1/auth/me", headers=auth("tok-newcomer"))
    assert me.status_code == 200 and me.json()["isActive"] is False and me.json()["role"] == "viewer"      # they can ask who they are
    blocked = db_client.get("/api/v1/leads", headers=auth("tok-newcomer"))
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "account_pending"
    assert db_client.get("/api/v1/customers", headers=auth("tok-newcomer")).status_code == 403


def test_a_newcomer_stays_blocked_because_there_is_no_one_to_approve_them(db_client, db_session, supabase):
    supabase.add("tok-owner", "owner@test.example")
    supabase.add("tok-newcomer", "newcomer@test.example")
    db_client.get("/api/v1/auth/me", headers=auth("tok-owner"))
    assert db_client.get("/api/v1/auth/me", headers=auth("tok-newcomer")).json()["isActive"] is False
    svc.reset_token_cache()
    assert db_client.get("/api/v1/leads", headers=auth("tok-newcomer")).status_code == 403
    assert db_client.get("/api/v1/leads", headers=auth("tok-owner")).status_code == 200


def test_owner_email_decides_who_may_claim_the_site(db_client, db_session, supabase):
    app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(update={"supabase_url": "https://project.supabase.test", "supabase_anon_key": "anon-key", "owner_email": "Real.Owner@test.example"})
    supabase.add("tok-squatter", "squatter@test.example")
    supabase.add("tok-real", "real.owner@test.example")
    squatter = db_client.get("/api/v1/auth/me", headers=auth("tok-squatter")).json()
    assert squatter["isActive"] is False and squatter["role"] == "viewer"                          # not the owner address: waits, even though it came first
    real = db_client.get("/api/v1/auth/me", headers=auth("tok-real")).json()
    assert real["role"] == "owner" and real["isActive"] is True


def test_a_good_answer_from_supabase_is_remembered_for_a_minute(db_client, supabase):
    supabase.add("tok-owner", "owner@test.example")
    for _ in range(5):
        db_client.get("/api/v1/leads", headers=auth("tok-owner"))
    assert supabase.calls == 1
    svc.reset_token_cache()
    db_client.get("/api/v1/leads", headers=auth("tok-owner"))
    assert supabase.calls == 2


def test_a_token_that_supabase_refuses_is_never_trusted_or_cached(db_client, supabase):
    assert db_client.get("/api/v1/leads", headers=auth("expired")).status_code == 401
    supabase.add("expired", "late@test.example")                                                   # it becomes valid later (a fresh sign-in)
    assert db_client.get("/api/v1/auth/me", headers=auth("expired")).status_code == 200


def test_an_unreachable_supabase_is_a_clear_503_not_a_wrong_answer(db_client, monkeypatch):
    def down(request, timeout):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(svc.urllib.request, "urlopen", down)
    r = db_client.get("/api/v1/leads", headers=auth("any"))
    assert r.status_code == 503 and r.json()["error"]["code"] == "auth_unreachable"


def test_missing_supabase_settings_say_so(db_client):
    app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(update={"supabase_url": None, "supabase_anon_key": None})
    r = db_client.get("/api/v1/leads", headers=auth("any"))
    assert r.status_code == 503 and r.json()["error"]["code"] == "auth_not_configured"
