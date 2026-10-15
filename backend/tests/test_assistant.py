"""AI assistant tests. OpenAI is never called: a fake model stands in for it."""

import json
from datetime import date, timedelta
from decimal import Decimal

import httpx2 as httpx
import openai
import pytest

from app.api.v1.assistant import get_assistant_model
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.main import app
from app.services import analytics as a
from app.services.assistant import MAX_HISTORY, ChatTurn, OpenAIModel
from app.services.assistant_context import build_context
from tests.conftest import requires_database
from tests.test_analytics_api import import_customers


class FakeModel:
    model = "fake-model"

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[ChatTurn]]] = []

    def answer(self, instructions: str, turns: list[ChatTurn]) -> str:
        self.calls.append((instructions, turns))
        return "Champions drive most revenue."


def ask(client, *messages: tuple[str, str]):
    return client.post(
        "/api/v1/assistant/chat",
        json={"messages": [{"role": r, "content": c} for r, c in messages]},
    )


# --- privacy of the data summary ---------------------------------------------

def test_context_never_contains_names_or_emails():
    as_of = date(2026, 10, 1)
    facts = [
        a.OrderFact(f"C{i}", f"Secret Person{i}", f"secret{i}@example.com",
                    as_of - timedelta(days=i * 7 + k * 40), Decimal("50"), "Shopify",
                    "Skincare", "US", None)
        for i in range(25) for k in range(1 + i % 3)
    ]
    text = json.dumps(build_context(a.build_snapshot(facts)), default=str)
    assert "Secret Person" not in text and "@example.com" not in text
    assert '"dataAsOf": "2026-10-01"' in text and "notAvailable" in text


# --- request validation (no database or AI needed) -------------------------------

@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_assistant_model] = FakeModel
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("messages", [
    [],
    [("assistant", "hello")],
    [("user", "x" * 2001)],
    [("user", "   ")],
])
def test_invalid_requests_are_rejected(client, messages):
    response = ask(client, *messages)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_not_configured_returns_503_without_calling_ai():
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    try:
        response = ask(TestClient(app), ("user", "Who will churn?"))
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "assistant_not_configured"


# --- with the database (rolled back) ----------------------------------------------

@requires_database
def test_no_data_gives_fixed_reply_without_ai_call(db_client):
    fake = FakeModel()
    app.dependency_overrides[get_assistant_model] = lambda: fake
    body = ask(db_client, ("user", "How is revenue?")).json()
    assert body["answeredBy"] == "system" and body["dataAsOf"] is None
    assert fake.calls == []


@requires_database
def test_answer_is_grounded_in_data_summary(db_client):
    import_customers(db_client, 30)
    fake = FakeModel()
    app.dependency_overrides[get_assistant_model] = lambda: fake
    history = [("user", f"q{i}") if i % 2 == 0 else ("assistant", f"a{i}") for i in range(14)]
    body = ask(db_client, *history, ("user", "Which segment earns most?")).json()

    assert body["reply"] == "Champions drive most revenue."
    assert body["answeredBy"] == "ai" and body["model"] == "fake-model"
    assert body["customerCount"] == 30 and body["dataAsOf"] is not None
    instructions, turns = fake.calls[0]
    assert "Answer ONLY from the JSON data summary" in instructions
    assert '"customerCount":30' in instructions
    assert "@example.com" not in instructions  # no emails sent to the AI
    assert len(turns) == MAX_HISTORY and turns[-1].content == "Which segment earns most?"


@requires_database
def test_status_reports_configuration_and_data(db_client):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, openai_api_key="sk-test")
    body = db_client.get("/api/v1/assistant/status").json()
    assert body == {"configured": True, "model": "gpt-6-luna", "dataAsOf": None, "customerCount": 0}


# --- provider error mapping --------------------------------------------------------

def _status_error(cls, status: int, body=None):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
    return cls("provider error", response=response, body=body)


@pytest.mark.parametrize("error, code, status", [
    (_status_error(openai.AuthenticationError, 401), "assistant_auth_failed", 502),
    (_status_error(openai.NotFoundError, 404), "assistant_model_not_found", 502),
    (_status_error(openai.RateLimitError, 429, {"code": "insufficient_quota"}), "assistant_quota_exceeded", 503),
    (_status_error(openai.RateLimitError, 429, {"code": "rate_limit_exceeded"}), "assistant_rate_limited", 503),
    (openai.APITimeoutError(request=httpx.Request("POST", "https://api.openai.com")), "assistant_timeout", 504),
    (openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com")), "assistant_unreachable", 503),
])
def test_provider_errors_become_clear_api_errors(monkeypatch, error, code, status):
    model = OpenAIModel(Settings(_env_file=None, openai_api_key="sk-test"))

    def fail(**_):
        raise error

    monkeypatch.setattr(model._client.responses, "create", fail)
    with pytest.raises(ApiError) as exc:
        model.answer("instructions", [ChatTurn("user", "hi")])
    assert (exc.value.code, exc.value.status_code) == (code, status)
    assert "sk-test" not in exc.value.message


def test_request_disables_storage_and_limits_output(monkeypatch):
    model = OpenAIModel(Settings(_env_file=None, openai_api_key="sk-test"))
    captured = {}

    class Reply:
        output_text = " Answer. "

    def create(**kwargs):
        captured.update(kwargs)
        return Reply()

    monkeypatch.setattr(model._client.responses, "create", create)
    assert model.answer("rules", [ChatTurn("user", "hi")]) == "Answer."
    assert captured["store"] is False and captured["max_output_tokens"] == 700
    assert captured["model"] == "gpt-6-luna" and captured["instructions"] == "rules"
