"""AI Business Assistant: answers questions using only the computed data summary.

The OpenAI key stays on the server. Requests use `store=False` so OpenAI does
not keep the conversation for later retrieval. Message text is never logged.
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
MAX_OUTPUT_TOKENS = 700

INSTRUCTIONS = """You are CustomerIQ's business assistant for an e-commerce store.

Rules:
- Answer ONLY from the JSON data summary provided below. Do not use outside knowledge
  about this business, and never invent numbers, customers, or trends.
- If the summary does not contain what is needed, say so plainly and suggest what data
  or feature would be required.
- Items under "notAvailable" are not available. Never estimate them. For example,
  for churn questions use the rule-based inactivity levels and say they describe
  behaviour rather than predict it.
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


def get_model(settings: Settings) -> AssistantModel:
    if not settings.assistant_configured:
        raise ApiError(
            503,
            "assistant_not_configured",
            "The AI assistant is not configured. Add OPENAI_API_KEY to backend/.env and restart the backend.",
        )
    return OpenAIModel(settings)


def build_instructions(context: dict) -> str:
    return INSTRUCTIONS + json.dumps(context, separators=(",", ":"), default=str)


def recent_turns(turns: list[ChatTurn]) -> list[ChatTurn]:
    return turns[-MAX_HISTORY:]
