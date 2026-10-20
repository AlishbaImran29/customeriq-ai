"""Response and request shapes of the Cash Tracker (camelCase, matching frontend/lib/api/cash.ts)."""

from datetime import date

from pydantic import Field

from app.schemas.imports import CamelModel, ImportRowError


class CourierCashOut(CamelModel):
    courier: str
    delivered_cod: float
    received: float
    pending: float
    unpaid_parcels: int               # pending + partly paid
    paid_parcels: int
    oldest_pending_days: int | None
    average_days_to_pay: float | None # None without enough fully paid parcels
    enough: bool
    needed: int
    credit: float                     # paid more than owed so far
    overdue_amount: float             # still owed on parcels older than the alert threshold
    overdue_parcels: int


class BucketOut(CamelModel):
    label: str                        # "0-7", "8-14", "15+"
    parcels: int
    amount: float


class TrackerOut(CamelModel):
    as_of: date
    alert_days: int
    source_used: str                  # "real" or "demo"
    real_cod_parcels: int
    demo_cod_parcels: int
    payments: int
    min_group_count: int
    delivered_cod: float
    received: float
    pending: float
    credit: float
    unpaid_parcels: int
    oldest_pending_days: int | None
    couriers: list[CourierCashOut]
    buckets: list[BucketOut]
    alerts: list[CourierCashOut]      # couriers owing money older than the threshold


class PendingRowOut(CamelModel):
    courier: str
    city: str | None
    reference: str
    delivered_on: date
    days_pending: int
    cod_amount: float
    paid: float
    still_owed: float
    status: str                       # "pending" or "partly_paid"


class PaymentImportOut(CamelModel):
    rows_in_file: int
    created: int
    updated: int
    rejected: int
    new_courier_names: list[str]
    error_count: int
    errors: list[ImportRowError]
    errors_truncated: bool


class PaymentIn(CamelModel):
    courier_name: str = Field(max_length=100)
    payment_date: date
    amount: float
    reference: str | None = Field(default=None, max_length=100)
    order_ids: str | None = Field(default=None, max_length=2000)


class PaymentSavedOut(CamelModel):
    courier: str
    payment_date: date
    amount: float


class PaymentsSummaryOut(CamelModel):
    payments: int
    demo_payments: int
