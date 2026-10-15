import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.assistant import AssistantStatus, ChatRequest, ChatResponse
from app.services.analytics_data import load_snapshot
from app.services.assistant import (
    AssistantModel,
    ChatTurn,
    build_instructions,
    get_model,
    recent_turns,
)
from app.services.assistant_context import build_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])

NO_DATA_REPLY = (
    "No customer data has been imported yet, so there is nothing to analyse. "
    "Import a CSV or Excel file of orders on the Import page, then ask again."
)


def get_assistant_model(settings: Settings = Depends(get_settings)) -> AssistantModel:
    """Overridable in tests; raises 503 when no API key is configured."""
    return get_model(settings)


@router.get("/status", response_model=AssistantStatus)
def status(settings: Settings = Depends(get_settings), db: Session = Depends(get_db)) -> AssistantStatus:
    """Whether the assistant can answer. Does not call the AI provider."""
    snapshot = load_snapshot(db)
    return AssistantStatus(
        configured=settings.assistant_configured,
        model=settings.openai_model if settings.assistant_configured else None,
        data_as_of=snapshot.as_of,
        customer_count=len(snapshot.customers),
    )


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    model: AssistantModel = Depends(get_assistant_model),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Answer a question using only the computed data summary (no names or emails)."""
    snapshot = load_snapshot(db)
    if snapshot.empty:
        return ChatResponse(
            reply=NO_DATA_REPLY, answered_by="system", model=None, data_as_of=None, customer_count=0
        )

    turns = recent_turns([ChatTurn(m.role, m.content) for m in request.messages])
    reply = model.answer(build_instructions(build_context(snapshot)), turns)
    # Counts only — never log questions or answers.
    logger.info("Assistant answered (%d turns in context)", len(turns))
    return ChatResponse(
        reply=reply,
        answered_by="ai",
        model=model.model,
        data_as_of=snapshot.as_of,
        customer_count=len(snapshot.customers),
    )
