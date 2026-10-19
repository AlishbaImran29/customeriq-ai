"""Response shapes for the shipments endpoints (camelCase, matching frontend/lib/api/shipments.ts)."""

from app.schemas.imports import CamelModel, ImportRowError


class ShipmentImportOut(CamelModel):
    rows_in_file: int
    created: int
    updated: int
    rejected: int
    linked_to_orders: int
    unlinked: int
    orders_updated: int                 # orders that received the courier's result (delivered / returned)
    new_courier_names: list[str]        # not in app/data/courier_names.json: kept as typed
    new_city_names: list[str]
    error_count: int
    errors: list[ImportRowError]
    errors_truncated: bool


class ShipmentSummaryOut(CamelModel):
    shipments: int
    linked_to_orders: int
    demo_shipments: int                 # made-up shipments (see scripts/generate_demo_shipments.py)
    couriers: list[str]                 # standard names plus any courier already in the data
    cities: list[str]


class DemoDeleteOut(CamelModel):
    deleted: int
