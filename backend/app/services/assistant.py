"""AI Business Assistant: answers questions using only the computed data summary.

Two providers, chosen with AI_PROVIDER: Anthropic Claude (default) or OpenAI.
API keys stay on the server and message text is never logged.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings
from app.core.errors import ApiError

logger = logging.getLogger(__name__)

MAX_HISTORY = 10
MAX_OUTPUT_TOKENS = 700          # OpenAI: visible answer only
CLAUDE_MAX_TOKENS = 16000        # Claude: includes its (hidden) thinking
CLAUDE_EFFORT = "medium"         # Q&A over a summary; raise to "high" if answers fall short
CLAUDE_FALLBACK_BETA = "server-side-fallback-2026-07-01"

INSTRUCTIONS = """You are CustomerIQ's business assistant for an e-commerce store.

Rules:
- Answer ONLY from the JSON data summary provided below. Do not use outside knowledge
  about this business, and never invent numbers, customers, or trends.
- If the summary does not contain what is needed, say so plainly and suggest what data
  or feature would be required.
- Items under "notAvailable" are not available. Never estimate them. If churn
  probability is listed there, use the rule-based inactivity levels instead and say they
  describe behaviour rather than predict it.
- Figures under "predictions" are MODEL ESTIMATES, not facts. Call them estimates,
  mention how well the model did on unseen data (its "validation"), and never state them
  with certainty. Keep actual figures and estimates clearly separate.
- Mention the data date (dataAsOf) when giving figures. Use the definitions provided.
- Customers are identified by customerId only. You have no names or contact details.
- Be concise: a short answer, then up to 4 bullet points with figures, then one
  practical next step. Use the currency symbol $ for money.

Data summary (JSON):
"""


@dataclass
class ChatTurn:
    role: str  # "user" or "assistant"
    content: str


class AssistantModel(Protocol):
    model: str

    def answer(self, instructions: str, turns: list[ChatTurn]) -> str: ...


class ClaudeModel:
    """Calls the Anthropic Messages API and maps failures to clear API errors.

    - The system prompt (rules + data summary) is marked for prompt caching, so
      follow-up questions on the same data reuse it at a lower price.
    - Server-side fallbacks: if the model declines for safety reasons, the API
      retries the request on a suitable fallback model within the same call.
    """

    def __init__(self, settings: Settings) -> None:
        import anthropic

        assert settings.anthropic_api_key is not None
        self.model = settings.anthropic_model
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout=settings.assistant_timeout_seconds,
            max_retries=1,
        )

    def answer(self, instructions: str, turns: list[ChatTurn]) -> str:
        import anthropic

        started = time.monotonic()
        try:
            response = self._client.beta.messages.create(
                model=self.model,
                max_tokens=CLAUDE_MAX_TOKENS,
                system=[{"type": "text", "text": instructions, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": t.role, "content": t.content} for t in turns],
                output_config={"effort": CLAUDE_EFFORT},
                betas=[CLAUDE_FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as exc:
            raise ApiError(
                502, "assistant_auth_failed",
                "Anthropic rejected the API key. Check ANTHROPIC_API_KEY in backend/.env.",
            ) from exc
        except anthropic.PermissionDeniedError as exc:
            raise ApiError(
                502, "assistant_permission_denied",
                "This Anthropic API key is not allowed to use this model or feature.",
            ) from exc
        except anthropic.NotFoundError as exc:
            raise ApiError(
                502, "assistant_model_not_found",
                f"The model '{self.model}' was not found. Check ANTHROPIC_MODEL in backend/.env.",
            ) from exc
        except anthropic.RateLimitError as exc:
            raise ApiError(
                503, "assistant_rate_limited",
                "The AI provider is busy (rate limit). Wait a moment and try again.",
            ) from exc
        except anthropic.APITimeoutError as exc:
            raise ApiError(504, "assistant_timeout", "The AI provider took too long to answer.") from exc
        except anthropic.APIConnectionError as exc:
            raise ApiError(
                503, "assistant_unreachable", "Could not reach the AI provider. Check the internet connection."
            ) from exc
        except anthropic.APIStatusError as exc:
            # Type and status only: enough to diagnose, never message content.
            logger.warning("Anthropic API error: status=%s type=%s", exc.status_code, exc.type)
            # Low credit balance can arrive as 402 billing_error or as a 400
            # invalid_request_error whose message names the credit balance.
            if exc.type == "billing_error" or "credit balance" in exc.message.lower():
                raise ApiError(
                    503, "assistant_quota_exceeded",
                    "The Anthropic account has no remaining credits. Add credits in the Claude Console (Billing).",
                ) from exc
            if exc.type == "overloaded_error":
                raise ApiError(
                    503, "assistant_rate_limited", "The AI provider is overloaded. Try again shortly."
                ) from exc
            raise ApiError(502, "assistant_provider_error", "The AI provider returned an error.") from exc
        finally:
            logger.info("Assistant call to %s took %.1fs", self.model, time.monotonic() - started)

        if response.stop_reason == "refusal":
            raise ApiError(
                422, "assistant_declined",
                "The AI declined to answer this question. Try rephrasing it as a business question.",
            )
        usage = response.usage
        logger.info(
            "Claude usage: input=%s cache_read=%s cache_write=%s output=%s",
            usage.input_tokens, usage.cache_read_input_tokens,
            usage.cache_creation_input_tokens, usage.output_tokens,
        )
        text = "\n\n".join(b.text for b in response.content if b.type == "text").strip()
        if not text:
            raise ApiError(502, "assistant_empty_reply", "The AI provider returned an empty answer.")
        return text


class OpenAIModel:
    """Calls the OpenAI Responses API and maps failures to clear API errors."""

    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI

        assert settings.openai_api_key is not None
        self.model = settings.openai_model
        self._client = OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.assistant_timeout_seconds,
            max_retries=1,
        )

    def answer(self, instructions: str, turns: list[ChatTurn]) -> str:
        import openai

        started = time.monotonic()
        try:
            response = self._client.responses.create(
                model=self.model,
                instructions=instructions,
                input=[{"role": t.role, "content": t.content} for t in turns],
                max_output_tokens=MAX_OUTPUT_TOKENS,
                store=False,
            )
        except openai.AuthenticationError as exc:
            raise ApiError(
                502, "assistant_auth_failed",
                "The AI provider rejected the API key. Check OPENAI_API_KEY in backend/.env.",
            ) from exc
        except openai.PermissionDeniedError as exc:
            raise ApiError(
                502, "assistant_permission_denied",
                "The OpenAI account does not have access to this model.",
            ) from exc
        except openai.NotFoundError as exc:
            raise ApiError(
                502, "assistant_model_not_found",
                f"The model '{self.model}' was not found. Check OPENAI_MODEL in backend/.env.",
            ) from exc
        except openai.RateLimitError as exc:
            if getattr(exc, "code", None) == "insufficient_quota":
                raise ApiError(
                    503, "assistant_quota_exceeded",
                    "The OpenAI account has no remaining credits. Add credits in the OpenAI dashboard.",
                ) from exc
            raise ApiError(
                503, "assistant_rate_limited",
                "The AI provider is busy (rate limit). Wait a moment and try again.",
            ) from exc
        except openai.APITimeoutError as exc:
            raise ApiError(504, "assistant_timeout", "The AI provider took too long to answer.") from exc
        except openai.APIConnectionError as exc:
            raise ApiError(
                503, "assistant_unreachable", "Could not reach the AI provider. Check the internet connection."
            ) from exc
        except openai.APIStatusError as exc:
            raise ApiError(502, "assistant_provider_error", "The AI provider returned an error.") from exc
        finally:
            logger.info("Assistant call to %s took %.1fs", self.model, time.monotonic() - started)

        text = (response.output_text or "").strip()
        if not text:
            raise ApiError(502, "assistant_empty_reply", "The AI provider returned an empty answer.")
        return text


KEY_NAMES = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def get_model(settings: Settings) -> AssistantModel:
    if not settings.assistant_configured:
        raise ApiError(
            503,
            "assistant_not_configured",
            f"The AI assistant is not configured. Add {KEY_NAMES[settings.ai_provider]} "
            "to backend/.env and restart the backend.",
        )
    if settings.ai_provider == "anthropic":
        return ClaudeModel(settings)
    return OpenAIModel(settings)


def build_instructions(context: dict) -> str:
    return INSTRUCTIONS + json.dumps(context, separators=(",", ":"), default=str)


def recent_turns(turns: list[ChatTurn]) -> list[ChatTurn]:
    """Last few turns, starting with a user turn (required by the Messages API)."""
    recent = turns[-MAX_HISTORY:]
    while recent and recent[0].role != "user":
        recent = recent[1:]
    return recent
