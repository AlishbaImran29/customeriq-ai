"""Request and response shapes of Launch Studio (camelCase, matching frontend/lib/api/launch.ts)."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.imports import CamelModel

Status = Literal["idea", "sourcing", "ready", "launched", "dropped"]


class ProjectIn(CamelModel):
    product_name: str = Field(min_length=2, max_length=120)
    category: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=4000)


class ProjectPatch(CamelModel):
    """Only the fields that are sent are changed."""

    product_name: str | None = Field(default=None, min_length=2, max_length=120)
    category: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=4000)
    status: Status | None = None


class ProjectOut(CamelModel):
    id: int
    product_name: str
    category: str | None
    status: Status
    notes: str | None
    launched_on: date | None
    created_at: datetime


class TrendPointOut(CamelModel):
    date: date
    value: float


class RelatedQueryOut(CamelModel):
    query: str
    value: str                          # as Google wrote it: "100", "Breakout", "+250%"
    kind: Literal["top", "rising"]


class TrendOut(CamelModel):
    id: int
    launch_project_id: int | None
    keyword: str
    region: str | None
    granularity: str | None
    points: list[TrendPointOut]
    related: list[RelatedQueryOut]
    label: Literal["rising", "stable", "falling"] | None      # None = "Not enough data yet"
    ratio: float | None                 # last 4 weeks average / the 8 weeks before
    created_at: datetime


class GrowthRowOut(CamelModel):
    product: str
    last: int
    before: int
    growth: float | None                # None = new: it sold nothing in the period before


class GrowthOut(CamelModel):
    days: int
    metric: str                         # "units", "orders" or "" (no data)
    source: str                         # "real", "demo" or ""
    period_end: date | None
    rows: list[GrowthRowOut]
    too_small: int
    min_group_count: int
    reason: str | None                  # no_data / not_enough_history


class IdeasIn(CamelModel):
    upload_ids: list[int] | None = Field(default=None, max_length=10)   # the trend files to use; default: the latest few
    force: bool = False                 # ask again instead of using the saved answer


class IdeaOut(CamelModel):
    name: str
    reason: str


class IdeasOut(CamelModel):
    label: Literal["AI suggestion"] = "AI suggestion"
    ideas: list[IdeaOut]
    cached: bool                        # True = the saved answer was used, nothing was paid for
    model: str | None
