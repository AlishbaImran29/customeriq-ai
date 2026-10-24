"""Launch Studio endpoints (step 1): launch projects, the Trend Finder, and AI product ideas."""

from datetime import date

from fastapi import APIRouter, Depends, Form, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_user
from app.api.v1.shipments import _read_limited
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import Order, User
from app.models.launch import AiCache, LaunchProject, TrendUpload
from app.schemas.launch import (
    GrowthOut, GrowthRowOut, IdeaOut, IdeasIn, IdeasOut, ProjectIn, ProjectOut, ProjectPatch, TrendOut, TrendPointOut,
    RelatedQueryOut,
)
from app.services import data_rules
from app.services.google_trends import parse_google_trends
from app.services.launch_ai import KIND_IDEAS, ask_for_ideas, build_inputs, cache_key
from app.services.product_growth import PERIODS, product_growth
from app.services.rate_limit import check_rate_limit
from app.services.trend_label import label_trend

router = APIRouter(prefix="/launch", tags=["launch"])

MAX_TREND_FILE = 2 * 1024 * 1024
MAX_PROJECTS = 500
IDEAS_PER_WINDOW = 10                    # AI idea requests per account in the window (each one costs money)
IDEAS_WINDOW_SECONDS = 600


# --- launch projects ---------------------------------------------------------------------------


def _project(db: Session, project_id: int) -> LaunchProject:
    project = db.get(LaunchProject, project_id)
    if project is None:
        raise ApiError(404, "project_not_found", "That launch project was not found.")
    return project


def _clean(text: str | None) -> str | None:
    text = (text or "").strip()
    return text or None


@router.get("/projects", response_model=list[ProjectOut], summary="All launch projects, newest first")
def list_projects(db: Session = Depends(get_db)) -> list[LaunchProject]:
    return list(db.scalars(select(LaunchProject).order_by(LaunchProject.created_at.desc(), LaunchProject.id.desc()).limit(MAX_PROJECTS)))


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED, summary="Start a launch project")
def create_project(body: ProjectIn, db: Session = Depends(get_db), user: User = Depends(require_user)) -> LaunchProject:
    name = body.product_name.strip()
    if len(name) < 2:
        raise ApiError(422, "invalid_name", "Give the product a name of at least 2 characters.")
    count = db.scalar(select(func.count()).select_from(LaunchProject)) or 0
    if count >= MAX_PROJECTS:
        raise ApiError(409, "too_many_projects", "You have reached the limit of launch projects. Delete old ones first.")
    project = LaunchProject(product_name=name, category=_clean(body.category), notes=_clean(body.notes), created_by=user.id)
    db.add(project)
    db.commit()
    return project


@router.patch("/projects/{project_id}", response_model=ProjectOut, summary="Change a launch project")
def update_project(project_id: int, body: ProjectPatch, db: Session = Depends(get_db)) -> LaunchProject:
    project = _project(db, project_id)
    sent = body.model_fields_set
    if "product_name" in sent and body.product_name:
        project.product_name = body.product_name.strip()
    if "category" in sent:
        project.category = _clean(body.category)
    if "notes" in sent:
        project.notes = _clean(body.notes)
    if "status" in sent and body.status:
        project.status = body.status
        if body.status == "launched" and project.launched_on is None:
            project.launched_on = date.today()
    db.commit()
    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a launch project and its trend files")
def delete_project(project_id: int, db: Session = Depends(get_db)) -> Response:
    db.delete(_project(db, project_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Trend Finder: Google Trends files ---------------------------------------------------------------


def _trend_out(t: TrendUpload) -> TrendOut:
    return TrendOut(
        id=t.id, launch_project_id=t.launch_project_id, keyword=t.keyword, region=t.region, granularity=t.granularity,
        points=[TrendPointOut(date=date.fromisoformat(d), value=v) for d, v in (t.points or [])],
        related=[RelatedQueryOut(**r) for r in (t.related or [])], label=t.label, ratio=t.ratio, created_at=t.created_at,
    )


@router.post("/trends/upload", response_model=list[TrendOut], status_code=status.HTTP_201_CREATED, summary="Upload a Google Trends CSV")
async def upload_trends(
    file: UploadFile, launch_project_id: int | None = Form(default=None), db: Session = Depends(get_db),
) -> list[TrendOut]:
    """The seller downloads the file from trends.google.com themselves: the app never fetches Google."""
    if launch_project_id is not None:
        _project(db, launch_project_id)
    content = await _read_limited(file)
    parsed = parse_google_trends(content)
    related = [{"query": r.query, "value": r.value, "kind": r.kind} for r in parsed.related]
    saved: list[TrendUpload] = []
    for index, one in enumerate(parsed.series):
        label, ratio = label_trend(one.points)
        saved.append(TrendUpload(
            launch_project_id=launch_project_id, keyword=one.keyword, region=one.region, granularity=one.granularity,
            points=[[d.isoformat(), v] for d, v in one.points], related=related if index == 0 else [], label=label, ratio=ratio,
        ))
    if not parsed.series and related:                      # a "related queries" file on its own
        saved.append(TrendUpload(launch_project_id=launch_project_id, keyword="Related queries", points=[], related=related))
    db.add_all(saved)
    db.commit()
    return [_trend_out(t) for t in saved]


@router.get("/trends", response_model=list[TrendOut], summary="The Google Trends files uploaded so far")
def list_trends(launch_project_id: int | None = Query(default=None), db: Session = Depends(get_db)) -> list[TrendOut]:
    stmt = select(TrendUpload).order_by(TrendUpload.created_at.desc(), TrendUpload.id.desc()).limit(50)
    if launch_project_id is not None:
        stmt = stmt.where(TrendUpload.launch_project_id == launch_project_id)
    return [_trend_out(t) for t in db.scalars(stmt)]


@router.delete("/trends/{trend_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove an uploaded trend")
def delete_trend(trend_id: int, db: Session = Depends(get_db)) -> Response:
    trend = db.get(TrendUpload, trend_id)
    if trend is None:
        raise ApiError(404, "trend_not_found", "That trend was not found.")
    db.delete(trend)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Trend Finder: the seller's own growing products ---------------------------------------------


@router.get("/growth", response_model=GrowthOut, summary="Products whose own sales grew fastest")
def growth(days: int = Query(30), db: Session = Depends(get_db)) -> GrowthOut:
    if days not in PERIODS:
        raise ApiError(422, "invalid_days", "days must be one of: " + ", ".join(str(p) for p in PERIODS) + ".")
    result = product_growth(db, days)
    return GrowthOut(
        days=result.days, metric=result.metric, source=result.source, period_end=result.period_end,
        rows=[GrowthRowOut(product=r.product, last=r.last, before=r.before, growth=r.growth) for r in result.rows],
        too_small=result.too_small, min_group_count=data_rules.MIN_GROUP_COUNT, reason=result.reason,
    )


# --- AI ideas ---------------------------------------------------------------------------------------


@router.post("/ideas", response_model=IdeasOut, summary="Ask the AI for product ideas (an AI suggestion)")
def ideas(
    body: IdeasIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings), user: User = Depends(require_user),
) -> IdeasOut:
    stmt = select(TrendUpload).order_by(TrendUpload.created_at.desc(), TrendUpload.id.desc())
    stmt = stmt.where(TrendUpload.id.in_(body.upload_ids)) if body.upload_ids else stmt.limit(3)
    trends = [{"keyword": t.keyword, "label": t.label, "related": t.related or []} for t in db.scalars(stmt) if t.keyword != "Related queries" or t.related]
    categories = [
        c for c in db.scalars(
            select(Order.product_category).where(Order.product_category.is_not(None)).group_by(Order.product_category)
            .order_by(func.count().desc()).limit(10)
        ) if c
    ]
    growing = [r.product for r in product_growth(db, 90).rows]
    if not trends and not categories and not growing:
        raise ApiError(422, "nothing_to_go_on", "Upload a Google Trends file first (or import some orders), so the AI has facts to work from.")
    inputs = build_inputs(trends, categories, growing)
    # A saved answer costs nothing, so only a real AI call counts against the limit.
    if body.force or db.get(AiCache, cache_key(KIND_IDEAS, inputs)) is None:
        check_rate_limit(f"ideas:{user.id}", limit=IDEAS_PER_WINDOW, window_seconds=IDEAS_WINDOW_SECONDS, what="for ideas")
    found, cached, model = ask_for_ideas(db, settings, inputs, force=body.force)
    return IdeasOut(ideas=[IdeaOut(**i) for i in found], cached=cached, model=model)
