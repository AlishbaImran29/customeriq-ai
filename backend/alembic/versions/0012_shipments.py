"""Courier Scorecard, step A1: the parcels handed to couriers.

A new table, so nothing that exists changes. Each shipment has a courier and a city (standard
names, see services/names.py), its dates and status, and optionally the COD amount, the courier's
fee and the reason a parcel came back. It links to its order where that can be worked out.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shipments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("external_id", sa.String(length=40), nullable=False),
        sa.Column("courier", sa.String(length=60), nullable=False),
        sa.Column("courier_raw", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("city_raw", sa.String(length=100), nullable=True),
        sa.Column("booked_date", sa.Date(), nullable=False),
        sa.Column("closed_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("return_reason", sa.Text(), nullable=True),
        sa.Column("refused", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("cod_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("courier_fee", sa.Numeric(12, 2), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_shipments_order_id_orders", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_shipments_customer_id_customers", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_shipments"),
        sa.CheckConstraint("status IN ('delivered', 'returned', 'in_transit', 'lost')", name="ck_shipments_shipment_status_known"),
        sa.CheckConstraint("closed_date IS NULL OR closed_date >= booked_date", name="ck_shipments_shipment_dates_in_order"),
        sa.CheckConstraint("cod_amount IS NULL OR cod_amount >= 0", name="ck_shipments_shipment_cod_non_negative"),
        sa.CheckConstraint("courier_fee IS NULL OR courier_fee >= 0", name="ck_shipments_shipment_fee_non_negative"),
    )
    op.create_index("ix_shipments_order_id", "shipments", ["order_id"])
    op.create_index("ix_shipments_customer_id", "shipments", ["customer_id"])
    op.create_index("ix_shipments_external_id", "shipments", ["external_id"], unique=True)
    op.create_index("ix_shipments_courier", "shipments", ["courier"])
    op.create_index("ix_shipments_city", "shipments", ["city"])
    op.create_index("ix_shipments_booked_date", "shipments", ["booked_date"])
    op.create_index("ix_shipments_courier_city", "shipments", ["courier", "city"])
    # Same protection as every other table (see 0005): the public REST API of a host such as
    # Supabase can read and write nothing; the app connects as the owner and is unaffected.
    op.execute('ALTER TABLE "shipments" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("shipments")
