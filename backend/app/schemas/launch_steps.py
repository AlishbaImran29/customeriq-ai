"""Request and response shapes of Launch Studio steps 2-6 (camelCase, matching frontend/lib/api/launch.ts)."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.imports import CamelModel

Language = Literal["ur", "roman_ur", "en"]


# --- step 2: vendors and quotes -------------------------------------------------------------------


class VendorIn(CamelModel):
    name: str = Field(min_length=2, max_length=120)
    whatsapp_phone: str | None = Field(default=None, max_length=40)       # any common way of writing a Pakistani mobile
    city: str | None = Field(default=None, max_length=100)
    categories: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=4000)


class VendorPatch(CamelModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    whatsapp_phone: str | None = Field(default=None, max_length=40)
    city: str | None = Field(default=None, max_length=100)
    categories: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=4000)


class VendorQualityOut(CamelModel):
    projects: int                      # launched projects that chose this vendor
    closed_orders: int
    return_rate: float | None          # None = "Not enough data yet"
    needed: int


class VendorOut(CamelModel):
    id: int
    name: str
    whatsapp_phone: str | None         # +92XXXXXXXXXX
    city: str | None
    categories: str | None
    notes: str | None
    quality: VendorQualityOut


class QuoteIn(CamelModel):
    vendor_id: int
    unit_price: float = Field(ge=0, le=100_000_000)
    moq: int | None = Field(default=None, ge=1, le=10_000_000)
    delivery_days: int | None = Field(default=None, ge=0, le=365)
    quality_notes: str | None = Field(default=None, max_length=2000)
    sample_received: bool = False
    quoted_on: date | None = None


class QuotePatch(CamelModel):
    unit_price: float | None = Field(default=None, ge=0, le=100_000_000)
    moq: int | None = Field(default=None, ge=1, le=10_000_000)
    delivery_days: int | None = Field(default=None, ge=0, le=365)
    quality_notes: str | None = Field(default=None, max_length=2000)
    sample_received: bool | None = None
    quoted_on: date | None = None


class QuoteOut(CamelModel):
    id: int
    vendor_id: int
    vendor_name: str
    launch_project_id: int
    unit_price: float
    moq: int | None
    delivery_days: int | None
    quality_notes: str | None
    sample_received: bool
    quoted_on: date
    cheapest: bool                     # marked with an icon and a label, never colour only
    fastest: bool
    chosen: bool                       # this quote's vendor is the project's chosen vendor


class ChooseVendorIn(CamelModel):
    vendor_id: int | None              # None = clear the choice


class QuoteRequestIn(CamelModel):
    project_id: int
    quantity: int = Field(ge=1, le=10_000_000)
    language: Language = "ur"
    force: bool = False


class MessageOut(CamelModel):
    label: Literal["AI suggestion"] = "AI suggestion"
    message: str
    whatsapp_phone: str | None
    cached: bool
    model: str | None


# --- step 3: competitor ads -------------------------------------------------------------------------


class AdOut(CamelModel):
    id: int
    launch_project_id: int
    page_name: str
    ad_text: str | None
    link: str | None
    price_seen: float | None
    offer_seen: str | None
    date_seen: date
    screenshot_url: str | None         # a link that expires after an hour
    has_screenshot: bool


class AdLibraryLinkOut(CamelModel):
    url: str


class AdFindingOut(CamelModel):
    id: int
    hook_type: str
    offer: str | None
    price: float | None
    cta: str | None
    cod_mentioned: bool
    language: str


class AnalysisIn(CamelModel):
    force: bool = False


class AnalysisOut(CamelModel):
    label: Literal["AI suggestion"] = "AI suggestion"
    ads: list[AdFindingOut]
    patterns: list[str]
    gaps: list[str]
    cached: bool
    model: str | None


# --- step 4: creatives ---------------------------------------------------------------------------------


class CreativeBrief(CamelModel):
    product_name: str = Field(min_length=2, max_length=120)
    features: list[str] = Field(default_factory=list, max_length=12)
    price: float | None = Field(default=None, ge=0, le=100_000_000)
    offer: str | None = Field(default=None, max_length=300)
    target_customer: str | None = Field(default=None, max_length=300)
    language: Language = "roman_ur"
    tone: str = Field(default="friendly", max_length=60)
    force: bool = False


class MetaAdOut(CamelModel):
    hook: str
    primary_text: str
    headline: str
    cta: str
    angle: Literal["price", "quality", "urgency", "social_proof", "cod_trust"]


class InstagramOut(CamelModel):
    caption: str
    hashtags: list[str]


class StatusOut(CamelModel):
    text: str


class CreativesOut(CamelModel):
    label: Literal["AI suggestion"] = "AI suggestion"
    meta_ads: list[MetaAdOut]
    instagram: InstagramOut | None
    whatsapp_status: StatusOut | None
    removed: int                       # suggestions dropped because they made claims that cannot be proven
    used_competitor_analysis: bool
    cached: bool
    model: str | None


class RegenerateIn(CamelModel):
    kind: Literal["meta_ad", "instagram", "whatsapp_status"]
    brief: CreativeBrief
    current: dict | None = None        # the version being replaced, so the AI writes a different one


class RegeneratedOut(CamelModel):
    label: Literal["AI suggestion"] = "AI suggestion"
    kind: Literal["meta_ad", "instagram", "whatsapp_status"]
    content: dict
    model: str | None


class CreativeIn(CamelModel):
    kind: Literal["meta_ad", "instagram", "whatsapp_status"]
    content: dict
    ai_generated: bool = True


class CreativePatch(CamelModel):
    content: dict


class CreativeOut(CamelModel):
    id: int
    launch_project_id: int
    kind: Literal["meta_ad", "instagram", "whatsapp_status"]
    content: dict
    ai_generated: bool
    created_at: datetime


# --- step 5: profit check ---------------------------------------------------------------------------------


class ProfitIn(CamelModel):
    cost: float
    price: float
    packing: float = 0
    courier_fee: float = 0
    return_shipping: float = 0
    return_rate: float
    ad_budget: float = 0


class ProfitOut(CamelModel):
    label: Literal["Estimate from your numbers"] = "Estimate from your numbers"
    profit_delivered: float
    loss_returned: float
    profit_per_order_placed: float
    margin: float | None
    break_even_cost_per_purchase: float | None
    break_even_roas: float | None
    orders_to_recover_budget: int | None
    warnings: list[str]


class ProfitDefaultsOut(CamelModel):
    cost: float | None                 # from the chosen vendor's quote
    cost_source: str | None            # the vendor's name
    return_rate: float | None          # the shop's real return rate (courier data), None = the seller must enter it
    return_rate_orders: int
    return_rate_needed: int
    saved: ProfitIn | None             # the inputs saved last time


# --- step 6: launch and results ----------------------------------------------------------------------------


class LaunchIn(CamelModel):
    launched_on: date | None = None    # default today


class LinkedProductIn(CamelModel):
    name: str = Field(min_length=2, max_length=120)


class LinkedProductOut(CamelModel):
    id: int
    name: str


class ProductNameOut(CamelModel):
    name: str


class ResultsOut(CamelModel):
    launched_on: date | None
    linked_products: list[str]
    orders: int
    revenue: float
    customers: int
    repeat_buyers: int
    closed_orders: int
    return_rate: float | None          # None = "Not enough data yet"
    return_needed: int
    real_profit_per_order: float | None
    expected_profit_per_order: float | None
    has_profit_inputs: bool
    min_group_count: int
    reason: str | None                 # not_launched / no_products
