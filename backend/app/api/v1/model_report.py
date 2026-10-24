"""Model Report Card endpoint."""

from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.imports import CamelModel
from app.services import model_report as mr

router = APIRouter(prefix="/models", tags=["models"])


class ReportRowOut(CamelModel):
    model: str
    label: str
    decision: str
    reason: str | None
    metric: str | None
    model_score: float | None
    baseline_score: float | None
    higher_is_better: bool
    test_size: int | None
    split_date: date | None


class HistoryOut(ReportRowOut):
    created_at: datetime


class ReportOut(CamelModel):
    rows: list[ReportRowOut]
    history: list[HistoryOut]


@router.get("/report", response_model=ReportOut, summary="Every model against its baseline, and the Shown/Hidden decision")
def report(db: Session = Depends(get_db)) -> ReportOut:
    """Builds the card from the current models and saves a history line for anything that changed."""
    rows = mr.current_rows(db)
    mr.record_changes(db, rows)
    return ReportOut(
        rows=[ReportRowOut.model_validate(r, from_attributes=True) for r in rows],
        history=[HistoryOut.model_validate(h, from_attributes=True) for h in mr.history(db)],
    )
