"""Meta Ads: status, audiences, delivered-only purchase events, ad spend import / sync, and true ROAS."""

from datetime import date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, UploadFile
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models.meta_event import MetaEvent
from app.schemas.imports import CamelModel
from app.services import meta_ads as service
from app.services import profit_analytics as pa

router = APIRouter(prefix="/meta-ads", tags=["meta-ads"])

Segment = Literal["champions", "lost", "buyers"]


class AudienceIn(CamelModel):
    segment: Segment
    name: str = Field(default="", max_length=100)
    confirm: bool = False


class EventOut(CamelModel):
    id: int
    order_id: int
    event_id: str
    status: str
    attempts: int
    error: str | None
    event_time: datetime
    sent_at: datetime | None


@router.get("/status", summary="What is connected, and whether test mode is on")
def status(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    flags = service.configured(settings)
    return {
        "testMode": settings.meta_ads_dry_run, "connected": flags, "readyToSend": all(flags.values()) and not settings.meta_ads_dry_run,
        "segments": service.SEGMENTS,
        "setupSteps": [
            "Create a Meta Business account and an app (developers.facebook.com).",
            "Add the Marketing API and create a long-lived access token with ads_management permission.",
            "Accept the Custom Audience Terms for your ad account in Business Manager.",
            "Put META_ADS_ACCESS_TOKEN, META_AD_ACCOUNT_ID (digits only) and META_PIXEL_ID in the backend settings.",
            "Try everything in test mode first, then set META_ADS_DRY_RUN=false.",
        ],
    }


@router.post("/audiences/preview", summary="Who would be sent (counts and a sample of hashes). Nothing is sent")
def audience_preview(body: AudienceIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    rows, left_out = service.audience_rows(db, body.segment)
    return {"segment": body.segment, "customers": len(rows), "leftOut": left_out, "sample": [[h[:10] + "…" if h else "" for h in r] for r in rows[:2]],
            "rule": "Only customers who agreed to WhatsApp or email and have a usable phone or email are included. Details are sent as SHA-256 hashes."}


@router.post("/audiences/push", summary="Send a segment to Meta as a Custom Audience (owner only; test mode sends nothing)")
def audience_push(body: AudienceIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    if not body.confirm:
        raise ApiError(422, "confirmation_required", "Please confirm: this shares hashed customer details with Meta.")
    return service.push_audience(db, settings, body.segment, body.name.strip() or f"CustomerIQ {body.segment}")


@router.get("/events", response_model=list[EventOut], summary="Purchase events for Meta, newest first")
def events(state: str | None = Query(None, pattern="^(pending|sent|dry_run|failed|skipped)$"), db: Session = Depends(get_db)) -> list[MetaEvent]:
    query = select(MetaEvent).order_by(MetaEvent.id.desc()).limit(200)
    if state:
        query = query.where(MetaEvent.status == state)
    return list(db.scalars(query))


@router.get("/events/summary", summary="Counts of purchase events by status")
def events_summary(db: Session = Depends(get_db)) -> dict[str, int]:
    counts = dict(db.execute(select(MetaEvent.status, func.count()).group_by(MetaEvent.status)).all())
    return {s: int(counts.get(s, 0)) for s in ("pending", "sent", "dry_run", "failed", "skipped")}


@router.post("/events/send", summary="Send the due purchase events now (owner only; test mode only prepares them)")
def events_send(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict[str, int]:
    counts = service.send_pending(db, settings)
    db.commit()
    return counts


@router.post("/ad-spend/import", summary="Import ad spend from a Meta export (CSV)")
async def import_spend(file: UploadFile, db: Session = Depends(get_db)) -> dict[str, Any]:
    result = service.import_spend_csv(db, await file.read(service.MAX_CSV_BYTES + 1))
    db.commit()
    return {"added": result.added, "updated": result.updated, "rejected": result.rejected, "errors": result.errors}


@router.post("/ad-spend/sync", summary="Read daily campaign spend from the Marketing API (owner only)")
def sync_spend(days: int = Query(14, ge=1, le=90), db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict[str, int]:
    end = pa.today_karachi()
    rows = service.sync_spend(db, settings, end - timedelta(days=days - 1), end)
    db.commit()
    return {"rows": rows}


@router.get("/roas", summary="Meta-reported revenue next to real delivered revenue, per campaign")
def roas(start: date | None = Query(None), end: date | None = Query(None), db: Session = Depends(get_db)) -> dict[str, Any]:
    default_start, default_end = pa.default_range()
    start, end = start or default_start, end or default_end
    if end < start or (end - start).days >= 366:
        raise ApiError(422, "invalid_range", "Choose a period of at most one year.")
    rows, untagged = service.roas(db, start, end)
    return {
        "start": start, "end": end, "untaggedOrders": untagged, "minGroupCount": service.data_rules.MIN_GROUP_COUNT,
        "campaigns": [{
            "campaign": r.campaign, "spend": float(r.spend), "metaPurchases": r.meta_purchases, "metaRevenue": float(r.meta_revenue) if r.meta_revenue is not None else None,
            "orders": r.orders, "delivered": r.delivered, "returned": r.returned, "realRevenue": float(r.real_revenue), "enough": r.enough,
            "metaRoas": r.meta_roas, "trueRoas": r.true_roas, "costPerDeliveredOrder": r.cost_per_delivered,
        } for r in rows],
        "note": "True ROAS counts only delivered orders that were not returned and that carry the campaign's name in their utm_campaign tag. Orders without a tag cannot be matched.",
    }
