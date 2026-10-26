"""Auto Messenger, part 4: new products and the campaigns that announce them."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_user
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import Campaign, CampaignRecipient, CatalogProduct, Customer, Message, User
from app.schemas.campaigns import (
    ApproveOut, AudienceConfig, AudienceOut, CampaignMessages, CampaignOut, CampaignPatch, DraftOut, GenerateIn, PreviewOut,
    ProductIn, ProductOut, RecipientCounts, RecipientOut, SampleOut, SegmentMessage,
)
from app.services.ai_cache import is_cached
from app.services.messaging import campaign_ai, campaigns
from app.services.messaging.render import check_template_text
from app.services.messaging.settings_store import get_row
from app.services.rate_limit import check_rate_limit

router = APIRouter(prefix="/messaging", tags=["messaging"])

AI_CALLS_PER_WINDOW = 10
AI_WINDOW_SECONDS = 600


def _campaign(db: Session, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise ApiError(404, "campaign_not_found", "That campaign was not found.")
    return campaign


def _draft(campaign: Campaign) -> None:
    if campaign.status != "draft":
        raise ApiError(409, "not_a_draft", "This campaign was already approved, so it cannot be changed. Cancel it and make a new one.")


def _config(campaign: Campaign) -> AudienceConfig:
    a = campaign.audience or {}
    return AudienceConfig(categories=a.get("categories", []), segments=[s for s in a.get("segments", []) if s in campaigns.SEGMENT_KEYS], include_category_buyers=a.get("include_category_buyers", True))


def _messages(campaign: Campaign) -> CampaignMessages | None:
    data = campaign.messages
    if not data:
        return None
    return CampaignMessages(
        messages={k: SegmentMessage(**{lang: v.get(lang, "") for lang in campaigns.LANGUAGES}) for k, v in (data.get("messages") or {}).items() if isinstance(v, dict)},
        subject=SegmentMessage(**{lang: (data.get("subject") or {}).get(lang, "") for lang in campaigns.LANGUAGES}),
    )


def _out(db: Session, campaign: Campaign) -> CampaignOut:
    counts = {s: n for s, n in db.execute(select(CampaignRecipient.status, func.count()).where(CampaignRecipient.campaign_id == campaign.id).group_by(CampaignRecipient.status))}
    product = db.get(CatalogProduct, campaign.product_id) if campaign.product_id else None
    return CampaignOut(
        id=campaign.id, name=campaign.name, status=campaign.status, product_id=campaign.product_id, product_name=product.name if product else None,  # type: ignore[arg-type]
        audience=_config(campaign), offer_text=campaign.offer_text, early_access_hours=campaign.early_access_hours, messages=_messages(campaign),
        ai_draft=campaign.ai_draft, approved_at=campaign.approved_at, completed_at=campaign.completed_at,
        counts=RecipientCounts(pending=int(counts.get("pending", 0)), sent=int(counts.get("sent", 0)), skipped=int(counts.get("skipped", 0)), total=int(sum(counts.values()))),
        created_at=campaign.created_at,
    )


def _audience_out(audience: campaigns.Audience) -> AudienceOut:
    return AudienceOut(candidates=audience.candidates, eligible=len(audience.members), no_consent=audience.no_consent, no_address=audience.no_address,
                       by_segment=audience.by_segment(), truncated=audience.truncated)


# --- products ----------------------------------------------------------------------------------------------------------------------


def _product_out(db: Session, p: CatalogProduct) -> ProductOut:
    campaign_id = db.scalar(select(Campaign.id).where(Campaign.product_id == p.id).order_by(Campaign.id).limit(1))
    return ProductOut(id=p.id, name=p.name, category=p.category, price=float(p.price) if p.price is not None else None, description=p.description, source=p.source, campaign_id=campaign_id)


@router.get("/products", response_model=list[ProductOut], summary="Products to announce")
def list_products(db: Session = Depends(get_db)) -> list[ProductOut]:
    return [_product_out(db, p) for p in db.scalars(select(CatalogProduct).order_by(CatalogProduct.id.desc()).limit(200))]


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED, summary="Add a product (this makes a DRAFT campaign)")
def add_product(body: ProductIn, db: Session = Depends(get_db)) -> ProductOut:
    product, _ = campaigns.create_product(
        db, name=body.name, category=body.category, price=Decimal(str(body.price)) if body.price is not None else None, description=body.description, source="manual",
    )
    db.commit()
    return _product_out(db, product)


# --- campaigns -------------------------------------------------------------------------------------------------------------------------


@router.get("/campaigns", response_model=list[CampaignOut], summary="Campaigns")
def list_campaigns(db: Session = Depends(get_db)) -> list[CampaignOut]:
    return [_out(db, c) for c in db.scalars(select(Campaign).order_by(Campaign.id.desc()).limit(100))]


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut, summary="One campaign")
def get_campaign(campaign_id: int, db: Session = Depends(get_db)) -> CampaignOut:
    return _out(db, _campaign(db, campaign_id))


@router.patch("/campaigns/{campaign_id}", response_model=CampaignOut, summary="Change a draft campaign")
def edit_campaign(campaign_id: int, body: CampaignPatch, db: Session = Depends(get_db)) -> CampaignOut:
    campaign = _campaign(db, campaign_id)
    _draft(campaign)
    sent = body.model_fields_set
    if "name" in sent and body.name:
        campaign.name = body.name.strip()
    if "audience" in sent and body.audience is not None:
        campaign.audience = {
            "categories": [c.strip() for c in body.audience.categories if c.strip()], "segments": list(body.audience.segments),
            "include_category_buyers": body.audience.include_category_buyers,
        }
        campaign.messages = None if campaign.ai_draft else campaign.messages        # a different audience may need different segments
    if "offer_text" in sent:
        campaign.offer_text = (body.offer_text or "").strip() or None
    if "early_access_hours" in sent and body.early_access_hours is not None:
        campaign.early_access_hours = body.early_access_hours
    db.commit()
    return _out(db, campaign)


@router.get("/campaigns/{campaign_id}/preview", response_model=PreviewOut, summary="The audience and 5 sample messages (nothing is sent)")
def preview_campaign(campaign_id: int, db: Session = Depends(get_db)) -> PreviewOut:
    campaign = _campaign(db, campaign_id)
    samples, audience = campaigns.preview(db, campaign)
    return PreviewOut(audience=_audience_out(audience), samples=[SampleOut(
        customer_name=s.customer_name, segment=s.segment, channel=s.channel, language=s.language, text=s.text, subject=s.subject, error=s.error,  # type: ignore[arg-type]
    ) for s in samples])


@router.post("/campaigns/{campaign_id}/generate", response_model=DraftOut, summary="The AI writes the base messages (an AI draft)")
def generate_messages(
    campaign_id: int, body: GenerateIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings), user: User = Depends(require_user),
) -> DraftOut:
    campaign = _campaign(db, campaign_id)
    _draft(campaign)
    audience = campaigns.compute_audience(db, campaign)
    segments = sorted(set(audience.by_segment()))
    if not segments:
        raise ApiError(422, "empty_audience", "Nobody in this audience has agreed to be messaged, so there is nothing to write for. Check the audience and the consent list first.")
    product = db.get(CatalogProduct, campaign.product_id) if campaign.product_id else None
    row = get_row(db)
    inputs = campaign_ai.build_inputs(campaign, product, segments, row.store_name)
    if body.force or not is_cached(db, campaign_ai.KIND, inputs):
        check_rate_limit(f"campaign-ai:{user.id}", limit=AI_CALLS_PER_WINDOW, window_seconds=AI_WINDOW_SECONDS, what="the AI")
    result, cached, model = campaign_ai.generate(db, settings, campaign, product, segments, row.store_name, force=body.force)
    campaign.messages, campaign.ai_draft = result, True
    db.commit()
    return DraftOut(campaign=_out(db, campaign), cached=cached, model=model)


@router.put("/campaigns/{campaign_id}/messages", response_model=CampaignOut, summary="Save your own wording")
def save_messages(campaign_id: int, body: CampaignMessages, db: Session = Depends(get_db)) -> CampaignOut:
    campaign = _campaign(db, campaign_id)
    _draft(campaign)
    clean: dict[str, dict[str, str]] = {}
    for key, entry in body.messages.items():
        if key not in campaigns.SEGMENT_LABELS:
            raise ApiError(422, "unknown_segment", f"Unknown segment: {key}.")
        clean[key] = {}
        for language in campaigns.LANGUAGES:
            text = getattr(entry, language).strip()
            if text:
                check_template_text(text)
            clean[key][language] = text
    subject = {lang: " ".join(getattr(body.subject, lang).split()) for lang in campaigns.LANGUAGES}
    for line in subject.values():
        check_template_text("x", line or None)
    campaign.messages, campaign.ai_draft = {"messages": clean, "subject": subject}, False         # the seller's wording: no longer an AI draft
    db.commit()
    return _out(db, campaign)


@router.post("/campaigns/{campaign_id}/approve", response_model=ApproveOut, summary="Approve: make the templates and schedule everyone")
def approve_campaign(campaign_id: int, db: Session = Depends(get_db)) -> ApproveOut:
    """Project rule 3: only after this are messages possible. Champions are first; the rest follow after the early-access hours."""
    campaign = _campaign(db, campaign_id)
    result = campaigns.approve(db, campaign)
    db.commit()
    return ApproveOut(**result)


@router.post("/campaigns/{campaign_id}/cancel", summary="Stop a campaign")
def cancel_campaign(campaign_id: int, db: Session = Depends(get_db)) -> dict:
    campaign = _campaign(db, campaign_id)
    if campaign.status in ("completed", "cancelled"):
        raise ApiError(409, "already_finished", "This campaign has already finished.")
    stopped = campaigns.cancel(db, campaign)
    db.commit()
    return {"stopped": stopped}


@router.delete("/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a draft campaign")
def delete_campaign(campaign_id: int, db: Session = Depends(get_db)) -> Response:
    campaign = _campaign(db, campaign_id)
    if campaign.status not in ("draft", "cancelled"):
        raise ApiError(409, "not_deletable", "Only a draft or a cancelled campaign can be deleted.")
    db.delete(campaign)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/campaigns/{campaign_id}/recipients", response_model=list[RecipientOut], summary="Who the campaign goes to, and when")
def list_recipients(campaign_id: int, show: str | None = Query(default=None, pattern="^(pending|sent|skipped)$"), db: Session = Depends(get_db)) -> list[RecipientOut]:
    _campaign(db, campaign_id)
    query = select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign_id).order_by(CampaignRecipient.scheduled_for, CampaignRecipient.id).limit(200)
    if show:
        query = query.where(CampaignRecipient.status == show)
    rows = list(db.scalars(query))
    names = {c.id: (" ".join(p for p in (c.first_name, c.last_name) if p) or c.external_id) for c in db.scalars(select(Customer).where(Customer.id.in_({r.customer_id for r in rows})))} if rows else {}
    statuses = {m.id: m.status for m in db.scalars(select(Message).where(Message.id.in_({r.message_id for r in rows if r.message_id})))} if rows else {}
    return [RecipientOut(id=r.id, customer_name=names.get(r.customer_id, "?"), segment=r.segment, stage=r.stage, scheduled_for=r.scheduled_for, status=r.status,  # type: ignore[arg-type]
                         reason=r.reason, message_status=statuses.get(r.message_id) if r.message_id else None) for r in rows]
