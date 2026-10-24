"""Shapes for journeys and the results dashboard (Auto Messenger parts 5 and 6), camelCase."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.imports import CamelModel


class StepIn(CamelModel):
    day: int = Field(ge=0, le=365)
    event: str = Field(min_length=3, max_length=40, pattern=r"^[a-z0-9_]+$")


class JourneyPatch(CamelModel):
    """Only the fields that are sent are changed."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=300)
    enabled: bool | None = None
    anchor: Literal["enrollment", "first_order"] | None = None
    steps: list[StepIn] | None = Field(default=None, min_length=1, max_length=6)
    loop_every_days: int | None = Field(default=None, ge=1, le=365)
    max_sends: int | None = Field(default=None, ge=1, le=50)
    max_per_30_days: int | None = Field(default=None, ge=1, le=30)
    grace_days: int | None = Field(default=None, ge=0, le=30)


class EnrollmentCounts(CamelModel):
    active: int
    holdout: int
    completed: int
    stopped: dict[str, int]            # by reason: ordered_again, replied, opted_out, segment_changed


class JourneyOut(CamelModel):
    id: int
    key: str
    name: str
    description: str | None
    trigger_segment: str
    anchor: Literal["enrollment", "first_order"]
    steps: list[StepIn]
    loop_every_days: int | None
    max_sends: int | None
    max_per_30_days: int | None
    grace_days: int
    enabled: bool
    counts: EnrollmentCounts
    messages_sent: int
    templates_ready: bool              # every step has an approved template


class SeedJourneysOut(CamelModel):
    journeys: int
    templates: int


class EnrollmentOut(CamelModel):
    id: int
    customer_name: str
    state: Literal["active", "completed", "stopped", "holdout"]
    holdout: bool
    stop_reason: str | None
    step: int
    sends: int
    next_run_at: datetime | None
    enrolled_at: datetime


class SchedulerOut(CamelModel):
    ok: bool
    results: dict[str, dict]


# --- results ------------------------------------------------------------------------------------------------


class GroupOut(CamelModel):
    id: int | None
    name: str
    sent: int
    delivered: int
    read: int
    replied: int
    failed: int
    skipped: int
    opt_outs: int
    orders: int
    revenue: float
    whatsapp_cost: float | None        # None = the price per message was not entered in the settings


class ComparisonOut(CamelModel):
    enough: bool                       # False = "Not enough data yet"
    messaged: int
    holdout: int
    needed: int
    messaged_rate: float | None
    holdout_rate: float | None
    difference: float | None
    low: float | None
    high: float | None
    could_be_chance: bool | None
    messaged_revenue: float | None
    holdout_revenue: float | None
    reason: str | None


class JourneyResultOut(CamelModel):
    journey_id: int
    name: str
    enabled: bool
    group: GroupOut | None
    comparison: ComparisonOut


class TotalsOut(CamelModel):
    sent: int
    delivered: int
    read: int
    replied: int
    failed: int
    skipped: int
    opt_outs: int
    orders: int
    revenue: float


class CostOut(CamelModel):
    utility_messages: int
    marketing_messages: int
    utility_rate: float | None
    marketing_rate: float | None
    total: float | None                # None until both rates that are needed were entered


class ResultsOut(CamelModel):
    days: int
    include_dry_run: bool
    min_group_count: int
    totals: TotalsOut
    cost: CostOut
    templates: list[GroupOut]
    campaigns: list[GroupOut]
    journeys: list[JourneyResultOut]
