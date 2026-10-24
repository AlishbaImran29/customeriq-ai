"""Launch Studio steps 2-6: vendors and quotes, competitor ads, creatives, profit check, launch and results.

Every AI call goes through `_ai`: it is rate limited per account, only a real call (not a saved answer) counts
against the limit, and every AI result comes back labelled "AI suggestion".
"""

import urllib.parse
from dataclasses import asdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_user
from app.api.v1.launch import _clean, _project
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import CompetitorAd, CreativeItem, LaunchProduct, LaunchProject, Order, ProductSale, User, Vendor, VendorQuote
from app.models.launch import AiCache
from app.models.order import LABEL_COURIER
from app.schemas.launch_steps import (
    AdFindingOut, AdLibraryLinkOut, AdOut, AnalysisIn, AnalysisOut, ChooseVendorIn, CreativeBrief, CreativeIn, CreativeOut,
    CreativePatch, CreativesOut, InstagramOut, LaunchIn, LinkedProductIn, LinkedProductOut, MessageOut, MetaAdOut,
    ProductNameOut, ProfitDefaultsOut, ProfitIn, ProfitOut, QuoteIn, QuoteOut, QuotePatch, QuoteRequestIn, RegenerateIn,
    RegeneratedOut, ResultsOut, StatusOut, VendorIn, VendorOut, VendorPatch, VendorQualityOut,
)
from app.services import data_rules, launch_ai, launch_ai_content as content
from app.services import profit as profit_service
from app.services.launch_ai import cache_key, is_cached, run_cached
from app.services.launch_results import name_key, project_results
from app.services.product_growth import split_products
from app.services.rate_limit import check_rate_limit
from app.services.supabase_storage import MAX_IMAGE_BYTES, delete_screenshot, signed_url, upload_screenshot
from app.services.vendors import best_quotes, clean_phone, vendor_quality

router = APIRouter(prefix="/launch", tags=["launch"])

AI_CALLS_PER_WINDOW = 20                 # real AI calls per account in the window (each one costs money)
AI_WINDOW_SECONDS = 600
MAX_ADS_PER_PROJECT = 40
MAX_ADS_SENT_TO_AI = 20
MAX_CREATIVES_PER_PROJECT = 100
META_AD_LIBRARY = "https://www.facebook.com/ads/library/"


def _ai(db: Session, settings: Settings, user: User, kind: str, inputs: dict, instructions: str, check, force: bool = False):
    """Run (or look up) one AI call. Only a call that really goes to the AI counts against the account's limit."""
    if force or not is_cached(db, kind, inputs):
        check_rate_limit(f"ai:{user.id}", limit=AI_CALLS_PER_WINDOW, window_seconds=AI_WINDOW_SECONDS, what="the AI")
    return run_cached(db, settings, kind, inputs, instructions, check, force=force)


def _get(db: Session, model, item_id: int, what: str):
    found = db.get(model, item_id)
    if found is None:
        raise ApiError(404, "not_found", f"That {what} was not found.")
    return found


# =========================== step 2: Vendor Book ===========================


def _vendor_out(db: Session, v: Vendor) -> VendorOut:
    q = vendor_quality(db, v.id)
    return VendorOut(
        id=v.id, name=v.name, whatsapp_phone=v.whatsapp_phone, city=v.city, categories=v.categories, notes=v.notes,
        quality=VendorQualityOut(projects=q.projects, closed_orders=q.closed_orders, return_rate=q.return_rate, needed=q.needed),
    )


@router.get("/vendors", response_model=list[VendorOut], summary="The vendor book")
def list_vendors(db: Session = Depends(get_db)) -> list[VendorOut]:
    return [_vendor_out(db, v) for v in db.scalars(select(Vendor).order_by(Vendor.name).limit(500))]


@router.post("/vendors", response_model=VendorOut, status_code=status.HTTP_201_CREATED, summary="Add a vendor")
def add_vendor(body: VendorIn, db: Session = Depends(get_db)) -> VendorOut:
    vendor = Vendor(
        name=body.name.strip(), whatsapp_phone=clean_phone(body.whatsapp_phone), city=_clean(body.city),
        categories=_clean(body.categories), notes=_clean(body.notes),
    )
    if len(vendor.name) < 2:
        raise ApiError(422, "invalid_name", "Give the vendor a name of at least 2 characters.")
    db.add(vendor)
    db.commit()
    return _vendor_out(db, vendor)


@router.patch("/vendors/{vendor_id}", response_model=VendorOut, summary="Change a vendor")
def edit_vendor(vendor_id: int, body: VendorPatch, db: Session = Depends(get_db)) -> VendorOut:
    vendor = _get(db, Vendor, vendor_id, "vendor")
    sent = body.model_fields_set
    if "name" in sent and body.name:
        vendor.name = body.name.strip()
    if "whatsapp_phone" in sent:
        vendor.whatsapp_phone = clean_phone(body.whatsapp_phone)
    for field in ("city", "categories", "notes"):
        if field in sent:
            setattr(vendor, field, _clean(getattr(body, field)))
    db.commit()
    return _vendor_out(db, vendor)


@router.delete("/vendors/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a vendor and its quotes")
def delete_vendor(vendor_id: int, db: Session = Depends(get_db)) -> Response:
    db.delete(_get(db, Vendor, vendor_id, "vendor"))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _quotes_out(db: Session, project: LaunchProject) -> list[QuoteOut]:
    quotes = list(db.scalars(select(VendorQuote).where(VendorQuote.launch_project_id == project.id).order_by(VendorQuote.unit_price, VendorQuote.id)))
    names = {v.id: v.name for v in db.scalars(select(Vendor).where(Vendor.id.in_({q.vendor_id for q in quotes})))} if quotes else {}
    cheapest, fastest = best_quotes(quotes)
    return [
        QuoteOut(
            id=q.id, vendor_id=q.vendor_id, vendor_name=names.get(q.vendor_id, "?"), launch_project_id=q.launch_project_id,
            unit_price=float(q.unit_price), moq=q.moq, delivery_days=q.delivery_days, quality_notes=q.quality_notes,
            sample_received=q.sample_received, quoted_on=q.quoted_on, cheapest=q.id in cheapest, fastest=q.id in fastest,
            chosen=project.chosen_vendor_id == q.vendor_id,
        )
        for q in quotes
    ]


@router.get("/projects/{project_id}/quotes", response_model=list[QuoteOut], summary="Quotes for a launch project")
def list_quotes(project_id: int, db: Session = Depends(get_db)) -> list[QuoteOut]:
    return _quotes_out(db, _project(db, project_id))


@router.post("/projects/{project_id}/quotes", response_model=list[QuoteOut], status_code=status.HTTP_201_CREATED, summary="Record a vendor quote")
def add_quote(project_id: int, body: QuoteIn, db: Session = Depends(get_db)) -> list[QuoteOut]:
    project = _project(db, project_id)
    _get(db, Vendor, body.vendor_id, "vendor")
    if body.quoted_on and body.quoted_on > date.today():
        raise ApiError(422, "invalid_date", "The quote date cannot be in the future.")
    db.add(VendorQuote(
        vendor_id=body.vendor_id, launch_project_id=project.id, unit_price=Decimal(str(body.unit_price)), moq=body.moq,
        delivery_days=body.delivery_days, quality_notes=_clean(body.quality_notes), sample_received=body.sample_received,
        quoted_on=body.quoted_on or date.today(),
    ))
    db.commit()
    return _quotes_out(db, project)


@router.patch("/quotes/{quote_id}", response_model=list[QuoteOut], summary="Change a quote")
def edit_quote(quote_id: int, body: QuotePatch, db: Session = Depends(get_db)) -> list[QuoteOut]:
    quote = _get(db, VendorQuote, quote_id, "quote")
    sent = body.model_fields_set
    if "unit_price" in sent and body.unit_price is not None:
        quote.unit_price = Decimal(str(body.unit_price))
    if "moq" in sent:
        quote.moq = body.moq
    if "delivery_days" in sent:
        quote.delivery_days = body.delivery_days
    if "sample_received" in sent and body.sample_received is not None:
        quote.sample_received = body.sample_received
    if "quoted_on" in sent and body.quoted_on is not None:
        if body.quoted_on > date.today():
            raise ApiError(422, "invalid_date", "The quote date cannot be in the future.")
        quote.quoted_on = body.quoted_on
    if "quality_notes" in sent:
        quote.quality_notes = _clean(body.quality_notes)
    db.commit()
    return _quotes_out(db, _project(db, quote.launch_project_id))


@router.delete("/quotes/{quote_id}", response_model=list[QuoteOut], summary="Delete a quote")
def delete_quote(quote_id: int, db: Session = Depends(get_db)) -> list[QuoteOut]:
    quote = _get(db, VendorQuote, quote_id, "quote")
    project = _project(db, quote.launch_project_id)
    db.delete(quote)
    db.commit()
    return _quotes_out(db, project)


@router.put("/projects/{project_id}/vendor", response_model=list[QuoteOut], summary="Choose the vendor for a launch project")
def choose_vendor(project_id: int, body: ChooseVendorIn, db: Session = Depends(get_db)) -> list[QuoteOut]:
    project = _project(db, project_id)
    if body.vendor_id is not None:
        _get(db, Vendor, body.vendor_id, "vendor")
    project.chosen_vendor_id = body.vendor_id
    db.commit()
    return _quotes_out(db, project)


@router.post("/vendors/{vendor_id}/quote-request", response_model=MessageOut, summary="An AI-written message asking a vendor for a quote")
def quote_request(
    vendor_id: int, body: QuoteRequestIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
    user: User = Depends(require_user),
) -> MessageOut:
    """The seller reads, edits and sends this message themselves from WhatsApp: the app never sends anything."""
    vendor, project = _get(db, Vendor, vendor_id, "vendor"), _project(db, body.project_id)
    inputs = {"product": project.product_name, "quantity": body.quantity, "language": body.language}
    result, cached, model = _ai(
        db, settings, user, content.KIND_VENDOR_MESSAGE, inputs, content.vendor_message_instructions(body.language),
        content.check_vendor_message, body.force,
    )
    return MessageOut(message=result["message"], whatsapp_phone=vendor.whatsapp_phone, cached=cached, model=model)


# =========================== step 3: Competitor Board ===========================


@router.get("/ad-library-link", response_model=AdLibraryLinkOut, summary="A link to the Meta Ad Library website for a keyword")
def ad_library_link(keyword: str = Query(min_length=2, max_length=100)) -> AdLibraryLinkOut:
    """Only builds a link; the seller opens it and looks at the ads on the website.

    The official Ad Library API does not return commercial ads outside the EU, and scraping the site is not
    allowed, so the seller views the ads there and saves the ones they want.
    """
    query = urllib.parse.urlencode({
        "active_status": "all", "ad_type": "all", "country": "PK", "q": keyword.strip(),
        "search_type": "keyword_unordered", "media_type": "all",
    })
    return AdLibraryLinkOut(url=f"{META_AD_LIBRARY}?{query}")


def _ad_out(settings: Settings, ad: CompetitorAd) -> AdOut:
    return AdOut(
        id=ad.id, launch_project_id=ad.launch_project_id, page_name=ad.page_name, ad_text=ad.ad_text, link=ad.link,
        price_seen=float(ad.price_seen) if ad.price_seen is not None else None, offer_seen=ad.offer_seen, date_seen=ad.date_seen,
        screenshot_url=signed_url(settings, ad.screenshot_path) if ad.screenshot_path else None, has_screenshot=bool(ad.screenshot_path),
    )


@router.get("/projects/{project_id}/ads", response_model=list[AdOut], summary="Saved competitor ads")
def list_ads(project_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> list[AdOut]:
    _project(db, project_id)
    ads = db.scalars(select(CompetitorAd).where(CompetitorAd.launch_project_id == project_id).order_by(CompetitorAd.date_seen.desc(), CompetitorAd.id.desc()))
    return [_ad_out(settings, a) for a in ads]


@router.post("/projects/{project_id}/ads", response_model=AdOut, status_code=status.HTTP_201_CREATED, summary="Save a competitor ad")
async def save_ad(
    project_id: int,
    page_name: str = Form(min_length=2, max_length=160),
    ad_text: str | None = Form(default=None, max_length=5000),
    link: str | None = Form(default=None, max_length=500),
    price_seen: float | None = Form(default=None, ge=0, le=100_000_000),
    offer_seen: str | None = Form(default=None, max_length=300),
    date_seen: date | None = Form(default=None),
    screenshot: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdOut:
    _project(db, project_id)
    if (db.scalar(select(func.count()).select_from(CompetitorAd).where(CompetitorAd.launch_project_id == project_id)) or 0) >= MAX_ADS_PER_PROJECT:
        raise ApiError(409, "too_many_ads", "This project already has the most ads it can keep. Delete some first.")
    if date_seen and date_seen > date.today():
        raise ApiError(422, "invalid_date", "The date seen cannot be in the future.")
    link = _clean(link)
    if link and not (link.startswith("https://") or link.startswith("http://")):
        raise ApiError(422, "invalid_link", "The link must start with https://", {"field": "link"})
    path = None
    if screenshot is not None and screenshot.filename:
        data = bytearray()
        while chunk := await screenshot.read(1024 * 1024):
            data.extend(chunk)
            if len(data) > MAX_IMAGE_BYTES:
                raise ApiError(413, "image_too_large", "The screenshot is larger than 3 MB. Use a smaller picture.")
        path = await run_in_threadpool(upload_screenshot, settings, project_id, bytes(data))
    ad = CompetitorAd(
        launch_project_id=project_id, page_name=page_name.strip(), ad_text=_clean(ad_text), screenshot_path=path, link=link,
        price_seen=Decimal(str(price_seen)) if price_seen is not None else None, offer_seen=_clean(offer_seen),
        date_seen=date_seen or date.today(),
    )
    db.add(ad)
    db.commit()
    return _ad_out(settings, ad)


@router.delete("/ads/{ad_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a saved ad")
def delete_ad(ad_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> Response:
    ad = _get(db, CompetitorAd, ad_id, "ad")
    path = ad.screenshot_path
    db.delete(ad)
    db.commit()
    if path:
        delete_screenshot(settings, path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _ads_for_ai(db: Session, project_id: int) -> list[dict]:
    ads = db.scalars(select(CompetitorAd).where(CompetitorAd.launch_project_id == project_id).order_by(CompetitorAd.id).limit(MAX_ADS_SENT_TO_AI))
    return [
        {"id": a.id, "page_name": a.page_name, "ad_text": (a.ad_text or "")[:600],
         "price": float(a.price_seen) if a.price_seen is not None else None, "offer": a.offer_seen}
        for a in ads if a.ad_text or a.offer_seen or a.price_seen is not None
    ]


def _analysis_out(result: dict, cached: bool, model: str | None) -> AnalysisOut:
    return AnalysisOut(ads=[AdFindingOut(**a) for a in result["ads"]], patterns=result["patterns"], gaps=result["gaps"], cached=cached, model=model)


@router.post("/projects/{project_id}/ads/analyse", response_model=AnalysisOut, summary="Analyse the saved ads with AI (an AI suggestion)")
def analyse_ads(
    project_id: int, body: AnalysisIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
    user: User = Depends(require_user),
) -> AnalysisOut:
    _project(db, project_id)
    ads = _ads_for_ai(db, project_id)
    if not ads:
        raise ApiError(422, "no_ads", "Save at least one competitor ad (with its text, price or offer) first.")
    result, cached, model = _ai(
        db, settings, user, content.KIND_AD_ANALYSIS, {"ads": ads}, content.AD_ANALYSIS_INSTRUCTIONS,
        content.make_ad_analysis_checker(ads), body.force,
    )
    return _analysis_out(result, cached, model)


def _cached_analysis(db: Session, project_id: int) -> dict | None:
    """The saved competitor analysis for the project's current ads, if there is one (never makes a new AI call)."""
    ads = _ads_for_ai(db, project_id)
    row = db.get(AiCache, cache_key(content.KIND_AD_ANALYSIS, {"ads": ads})) if ads else None
    return row.payload["result"] if row else None


# =========================== step 4: Creative Studio ===========================


def _brief_inputs(brief: CreativeBrief, analysis: dict | None) -> dict:
    inputs = {
        "product": brief.product_name.strip(), "features": [f.strip() for f in brief.features if f.strip()][:12],
        "price": brief.price, "offer": _clean(brief.offer), "target_customer": _clean(brief.target_customer),
        "language": content.LANGUAGES[brief.language], "tone": brief.tone.strip() or "friendly",
    }
    if analysis:
        inputs["competitor_findings"] = {"patterns": analysis["patterns"], "gaps": analysis["gaps"]}
    return inputs


@router.post("/projects/{project_id}/creatives/generate", response_model=CreativesOut, summary="Generate ad copy with AI (AI suggestions, not saved)")
def generate_creatives(
    project_id: int, brief: CreativeBrief, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
    user: User = Depends(require_user),
) -> CreativesOut:
    _project(db, project_id)
    analysis = _cached_analysis(db, project_id)
    result, cached, model = _ai(
        db, settings, user, content.KIND_CREATIVES, _brief_inputs(brief, analysis), content.CREATIVES_INSTRUCTIONS,
        content.check_creatives, brief.force,
    )
    return CreativesOut(
        meta_ads=[MetaAdOut(**a) for a in result["meta_ads"]],
        instagram=InstagramOut(**result["instagram"]) if result["instagram"] else None,
        whatsapp_status=StatusOut(**result["whatsapp_status"]) if result["whatsapp_status"] else None,
        removed=result["removed"], used_competitor_analysis=analysis is not None, cached=cached, model=model,
    )


@router.post("/projects/{project_id}/creatives/regenerate", response_model=RegeneratedOut, summary="Write a new version of one item (AI suggestion)")
def regenerate_creative(
    project_id: int, body: RegenerateIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
    user: User = Depends(require_user),
) -> RegeneratedOut:
    _project(db, project_id)
    inputs = {**_brief_inputs(body.brief, _cached_analysis(db, project_id)), "item": body.kind, "earlier_version": body.current}
    instructions = content.CREATIVE_ONE_INSTRUCTIONS + (
        " The item is: " + {"meta_ad": 'a Meta ad {"meta_ad":{"hook","primary_text","headline","cta","angle"}} (angle is one of '
                            + ", ".join(content.ANGLES) + ")",
                            "instagram": 'an Instagram post {"instagram":{"caption","hashtags"}}',
                            "whatsapp_status": 'a WhatsApp status {"whatsapp_status":"text"}'}[body.kind]
    )
    # Always a fresh call (the point is a different answer), so it counts against the limit.
    result, _, model = _ai(db, settings, user, content.KIND_CREATIVE_ONE, inputs, instructions, content.make_one_checker(body.kind), True)
    return RegeneratedOut(kind=body.kind, content=result, model=model)


def _clean_content(kind: str, data: dict) -> dict:
    """The shape of a saved creative, whatever the seller edited it to. Wrong shapes are refused."""
    def text(key: str, high: int, required: bool = True) -> str | None:
        value = data.get(key)
        if value is None and not required:
            return None
        if not isinstance(value, str) or not (1 <= len(value.strip()) <= high):
            raise ApiError(422, "invalid_content", f"{key}: write between 1 and {high} characters.", {"field": key})
        return value.strip()

    if kind == "meta_ad":
        angle = data.get("angle")
        if angle not in content.ANGLES:
            raise ApiError(422, "invalid_content", "angle: choose one of the angles.", {"field": "angle"})
        return {"hook": text("hook", 200), "primary_text": text("primary_text", 1200), "headline": text("headline", 100), "cta": text("cta", 40), "angle": angle}
    if kind == "instagram":
        tags = data.get("hashtags", [])
        if not isinstance(tags, list) or len(tags) > 30 or not all(isinstance(t, str) and len(t) <= 60 for t in tags):
            raise ApiError(422, "invalid_content", "hashtags: a list of up to 30 short words.", {"field": "hashtags"})
        return {"caption": text("caption", 2000), "hashtags": [t.strip() for t in tags if t.strip()]}
    return {"text": text("text", 700)}


def _creative_out(c: CreativeItem) -> CreativeOut:
    return CreativeOut(id=c.id, launch_project_id=c.launch_project_id, kind=c.kind, content=c.content, ai_generated=c.ai_generated, created_at=c.created_at)  # type: ignore[arg-type]


@router.get("/projects/{project_id}/creatives", response_model=list[CreativeOut], summary="Saved ad content")
def list_creatives(project_id: int, db: Session = Depends(get_db)) -> list[CreativeOut]:
    _project(db, project_id)
    return [_creative_out(c) for c in db.scalars(select(CreativeItem).where(CreativeItem.launch_project_id == project_id).order_by(CreativeItem.id.desc()))]


@router.post("/projects/{project_id}/creatives", response_model=CreativeOut, status_code=status.HTTP_201_CREATED, summary="Save ad content to the project")
def save_creative(project_id: int, body: CreativeIn, db: Session = Depends(get_db)) -> CreativeOut:
    _project(db, project_id)
    if (db.scalar(select(func.count()).select_from(CreativeItem).where(CreativeItem.launch_project_id == project_id)) or 0) >= MAX_CREATIVES_PER_PROJECT:
        raise ApiError(409, "too_many_creatives", "This project already has the most saved ad content it can keep. Delete some first.")
    item = CreativeItem(launch_project_id=project_id, kind=body.kind, content=_clean_content(body.kind, body.content), ai_generated=body.ai_generated)
    db.add(item)
    db.commit()
    return _creative_out(item)


@router.patch("/creatives/{creative_id}", response_model=CreativeOut, summary="Edit saved ad content")
def edit_creative(creative_id: int, body: CreativePatch, db: Session = Depends(get_db)) -> CreativeOut:
    item = _get(db, CreativeItem, creative_id, "ad content")
    item.content = _clean_content(item.kind, body.content)
    item.ai_generated = False                                  # the seller has changed it: it is theirs now
    db.commit()
    return _creative_out(item)


@router.delete("/creatives/{creative_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete saved ad content")
def delete_creative(creative_id: int, db: Session = Depends(get_db)) -> Response:
    db.delete(_get(db, CreativeItem, creative_id, "ad content"))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =========================== step 5: Profit Check ===========================


def _profit_out(result: profit_service.ProfitResult) -> ProfitOut:
    return ProfitOut(**asdict(result))


@router.post("/profit/calculate", response_model=ProfitOut, summary="Work out the profit for some numbers (nothing is saved)")
def calculate_profit(body: ProfitIn) -> ProfitOut:
    return _profit_out(profit_service.calculate(profit_service.ProfitInputs(**body.model_dump())))


@router.put("/projects/{project_id}/profit", response_model=ProfitOut, summary="Save a project's profit inputs")
def save_profit(project_id: int, body: ProfitIn, db: Session = Depends(get_db)) -> ProfitOut:
    project = _project(db, project_id)
    inputs = profit_service.ProfitInputs(**body.model_dump())
    result = profit_service.calculate(inputs)                 # refuses numbers that cannot be real before anything is saved
    project.profit_inputs = asdict(inputs)
    db.commit()
    return _profit_out(result)


@router.get("/projects/{project_id}/profit-defaults", response_model=ProfitDefaultsOut, summary="Starting values for the profit check")
def profit_defaults(project_id: int, db: Session = Depends(get_db)) -> ProfitDefaultsOut:
    project = _project(db, project_id)
    cost = cost_source = None
    if project.chosen_vendor_id:
        quote = db.scalar(select(VendorQuote).where(VendorQuote.launch_project_id == project.id, VendorQuote.vendor_id == project.chosen_vendor_id).order_by(VendorQuote.quoted_on.desc(), VendorQuote.id.desc()))
        vendor = db.get(Vendor, project.chosen_vendor_id)
        if quote is not None and vendor is not None:
            cost, cost_source = float(quote.unit_price), vendor.name
    # The shop's real return rate: only orders whose outcome came from courier data (a real delivered or returned result).
    closed = db.scalar(select(func.count()).select_from(Order).where(Order.label_source == LABEL_COURIER, Order.outcome.in_(("delivered", "returned")))) or 0
    rate = None
    if data_rules.enough(closed):
        returned = db.scalar(select(func.count()).select_from(Order).where(Order.label_source == LABEL_COURIER, Order.outcome == "returned")) or 0
        rate = round(returned / closed, 4)
    saved = ProfitIn(**project.profit_inputs) if project.profit_inputs else None
    return ProfitDefaultsOut(
        cost=cost, cost_source=cost_source, return_rate=rate, return_rate_orders=int(closed),
        return_rate_needed=data_rules.more_needed(int(closed)), saved=saved,
    )


# =========================== step 6: Launch and results ===========================


@router.post("/projects/{project_id}/launch", summary="Mark a project as launched")
def mark_launched(project_id: int, body: LaunchIn, db: Session = Depends(get_db)) -> dict:
    project = _project(db, project_id)
    when = body.launched_on or date.today()
    if when > date.today():
        raise ApiError(422, "invalid_date", "The launch date cannot be in the future.")
    project.status, project.launched_on = "launched", when
    db.commit()
    return {"status": project.status, "launchedOn": when.isoformat()}


@router.get("/projects/{project_id}/products", response_model=list[LinkedProductOut], summary="Products linked to a launch project")
def list_linked(project_id: int, db: Session = Depends(get_db)) -> list[LaunchProduct]:
    _project(db, project_id)
    return list(db.scalars(select(LaunchProduct).where(LaunchProduct.launch_project_id == project_id).order_by(LaunchProduct.name)))


@router.post("/projects/{project_id}/products", response_model=list[LinkedProductOut], status_code=status.HTTP_201_CREATED, summary="Link a product name from your orders")
def link_product(project_id: int, body: LinkedProductIn, db: Session = Depends(get_db)) -> list[LaunchProduct]:
    _project(db, project_id)
    name = " ".join(body.name.split())
    key = name_key(name)
    if len(key) < 2:
        raise ApiError(422, "invalid_name", "Give the product a name of at least 2 characters.")
    if db.scalar(select(LaunchProduct.id).where(LaunchProduct.launch_project_id == project_id, LaunchProduct.name_key == key)) is None:
        if (db.scalar(select(func.count()).select_from(LaunchProduct).where(LaunchProduct.launch_project_id == project_id)) or 0) >= 20:
            raise ApiError(409, "too_many_products", "A launch project can be linked to at most 20 product names.")
        db.add(LaunchProduct(launch_project_id=project_id, name=name, name_key=key))
        db.commit()
    return list_linked(project_id, db)


@router.delete("/projects/{project_id}/products/{link_id}", response_model=list[LinkedProductOut], summary="Unlink a product name")
def unlink_product(project_id: int, link_id: int, db: Session = Depends(get_db)) -> list[LaunchProduct]:
    _project(db, project_id)
    link = db.get(LaunchProduct, link_id)
    if link is None or link.launch_project_id != project_id:
        raise ApiError(404, "not_found", "That linked product was not found.")
    db.delete(link)
    db.commit()
    return list_linked(project_id, db)


def _like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/product-names", response_model=list[ProductNameOut], summary="Product names in your orders and sales that match some letters")
def product_names(q: str = Query(min_length=2, max_length=60), db: Session = Depends(get_db)) -> list[ProductNameOut]:
    wanted = q.strip().lower()
    found: dict[str, str] = {}
    for text in db.scalars(select(Order.products).where(Order.products.ilike(f"%{_like(wanted)}%", escape="\\")).limit(500)):
        for name in split_products(text):
            if wanted in name.lower():
                found.setdefault(name.lower(), name)
    for name in db.scalars(select(ProductSale.product).distinct().where(ProductSale.product.ilike(f"%{_like(wanted)}%", escape="\\")).limit(30)):
        found.setdefault(name.lower(), name)
    return [ProductNameOut(name=n) for n in sorted(found.values())[:20]]


@router.get("/projects/{project_id}/results", response_model=ResultsOut, summary="Real results of a launched project")
def results(project_id: int, db: Session = Depends(get_db)) -> ResultsOut:
    r = project_results(db, _project(db, project_id))
    return ResultsOut(
        launched_on=r.launched_on, linked_products=r.linked_products, orders=r.orders, revenue=r.revenue, customers=r.customers,
        repeat_buyers=r.repeat_buyers, closed_orders=r.closed_orders, return_rate=r.return_rate, return_needed=r.return_needed,
        real_profit_per_order=r.real_profit_per_order, expected_profit_per_order=r.expected_profit_per_order,
        has_profit_inputs=r.has_profit_inputs, min_group_count=data_rules.MIN_GROUP_COUNT, reason=r.reason,
    )
