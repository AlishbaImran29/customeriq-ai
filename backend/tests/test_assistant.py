"""AI assistant tests. OpenAI is never called: a fake model stands in for it."""

import json
from datetime import date, timedelta
from decimal import Decimal

from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import openai
import pytest

from app.api.v1.assistant import get_assistant_model
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.main import app
from app.services import analytics as a
from app.services.assistant import (
    CLAUDE_FALLBACK_BETA,
    MAX_HISTORY,
    ChatTurn,
    ClaudeModel,
    OpenAIModel,
    get_model,
    recent_turns,
)
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
    error = response.json()["error"]
    assert error["code"] == "assistant_not_configured" and "ANTHROPIC_API_KEY" in error["message"]


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
    assert turns[0].role == "user" and len(turns) <= MAX_HISTORY
    assert turns[-1].content == "Which segment earns most?"


@requires_database
def test_status_reports_configuration_and_data(db_client):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, anthropic_api_key="sk-ant-test")
    body = db_client.get("/api/v1/assistant/status").json()
    assert body == {
        "provider": "anthropic", "configured": True, "model": "claude-opus-5-5",
        "dataAsOf": None, "customerCount": 0,
    }


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


# --- provider selection -------------------------------------------------------------

def test_recent_turns_start_with_a_user_message():
    # 11 alternating turns: the last 10 begin with an assistant turn, which is dropped.
    turns = [ChatTurn("assistant" if i % 2 else "user", str(i)) for i in range(11)]
    recent = recent_turns(turns)
    assert recent[0].role == "user" and recent[-1].content == "10" and len(recent) == 9


def test_provider_selection():
    assert isinstance(get_model(Settings(_env_file=None, anthropic_api_key="sk-ant-test")), ClaudeModel)
    openai_settings = Settings(_env_file=None, ai_provider="openai", openai_api_key="sk-test")
    assert isinstance(get_model(openai_settings), OpenAIModel)
    # An OpenAI key alone does not configure the default (Claude) provider.
    with pytest.raises(ApiError) as exc:
        get_model(Settings(_env_file=None, openai_api_key="sk-test"))
    assert exc.value.code == "assistant_not_configured" and "ANTHROPIC_API_KEY" in exc.value.message


# --- Claude (Anthropic) ------------------------------------------------------------------

def claude() -> ClaudeModel:
    return ClaudeModel(Settings(_env_file=None, anthropic_api_key="sk-ant-test"))


def claude_reply(*blocks, stop_reason="end_turn"):
    usage = SimpleNamespace(input_tokens=10, cache_read_input_tokens=0,
                            cache_creation_input_tokens=900, output_tokens=40)
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason, usage=usage)


def test_claude_request_uses_caching_fallbacks_and_effort(monkeypatch):
    model = claude()
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return claude_reply(
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=" Champions lead. "),
        )

    monkeypatch.setattr(model._client.beta.messages, "create", create)
    assert model.answer("rules + data", [ChatTurn("user", "hi")]) == "Champions lead."
    assert captured["model"] == "claude-opus-5-5"
    assert captured["system"] == [
        {"type": "text", "text": "rules + data", "cache_control": {"type": "ephemeral"}}
    ]
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["fallbacks"] == "default" and captured["betas"] == [CLAUDE_FALLBACK_BETA]
    assert captured["output_config"] == {"effort": "medium"} and captured["max_tokens"] == 16000
    assert "thinking" not in captured and "temperature" not in captured


def test_claude_refusal_becomes_clear_error(monkeypatch):
    model = claude()
    monkeypatch.setattr(model._client.beta.messages, "create",
                        lambda **_: claude_reply(stop_reason="refusal"))
    with pytest.raises(ApiError) as exc:
        model.answer("rules", [ChatTurn("user", "hi")])
    assert exc.value.code == "assistant_declined"


def _anthropic_error(cls, status: int, error_type: str):
    body = {"type": "error", "error": {"type": error_type, "message": "provider error"}}
    response = httpx.Response(
        status, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"), json=body
    )
    return cls("provider error", response=response, body=body)


_request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.parametrize("error, code, status", [
    (_anthropic_error(anthropic.AuthenticationError, 401, "authentication_error"), "assistant_auth_failed", 502),
    (_anthropic_error(anthropic.PermissionDeniedError, 403, "permission_error"), "assistant_permission_denied", 502),
    (_anthropic_error(anthropic.NotFoundError, 404, "not_found_error"), "assistant_model_not_found", 502),
    (_anthropic_error(anthropic.RateLimitError, 429, "rate_limit_error"), "assistant_rate_limited", 503),
    (_anthropic_error(anthropic.APIStatusError, 402, "billing_error"), "assistant_quota_exceeded", 503),
    (_anthropic_error(anthropic.InternalServerError, 529, "overloaded_error"), "assistant_rate_limited", 503),
    (_anthropic_error(anthropic.InternalServerError, 500, "api_error"), "assistant_provider_error", 502),
    (anthropic.APITimeoutError(request=_request), "assistant_timeout", 504),
    (anthropic.APIConnectionError(request=_request), "assistant_unreachable", 503),
])
def test_claude_errors_become_clear_api_errors(monkeypatch, error, code, status):
    model = claude()

    def fail(**_):
        raise error

    monkeypatch.setattr(model._client.beta.messages, "create", fail)
    with pytest.raises(ApiError) as exc:
        model.answer("rules", [ChatTurn("user", "hi")])
    assert (exc.value.code, exc.value.status_code) == (code, status)
    assert "sk-ant-test" not in exc.value.message
