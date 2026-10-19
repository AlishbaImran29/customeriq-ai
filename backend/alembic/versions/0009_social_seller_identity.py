"""Social Seller Mode, step 1: a clean sales channel, and customers known by phone number.

- orders.sales_channel: one of instagram, whatsapp, facebook, website, other. Existing orders
  are filled in from their free-text `channel` (which is left exactly as it was, so the Revenue
  page does not change). The words matched here mirror backend/app/services/channels.py.
- customers.email may now be empty: a seller on WhatsApp or Instagram has a phone number,
  not an email address.
- customers.phone_normalised: the Pakistani mobile number as +923XXXXXXXXX. It is the key that
  merges repeat customers, so it is unique (only where it is set). Existing customers keep NULL
  here; it is filled in the next time they appear in an import with a phone number.

Nothing is deleted and no existing value changes (only the new column is filled).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHANNELS = "('instagram', 'whatsapp', 'facebook', 'website', 'other')"


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("sales_channel", sa.String(length=20), server_default="other", nullable=False)
    )
    # Same rules as channels.normalise_channel, in the same order (first match wins).
    op.execute(
        """
        UPDATE orders SET sales_channel = CASE
            WHEN channel ~* 'insta|\\mig\\M' THEN 'instagram'
            WHEN channel ~* 'whats\\s*app|\\mwa\\M' THEN 'whatsapp'
            WHEN channel ~* 'facebook|\\mfb\\M' THEN 'facebook'
            WHEN channel ~* 'web|shopify|woocommerce|magento|online|\\msite\\M' THEN 'website'
            ELSE 'other'
        END
        WHERE channel IS NOT NULL
        """
    )
    op.create_check_constraint("order_sales_channel_known", "orders", f"sales_channel IN {CHANNELS}")

    op.alter_column("customers", "email", existing_type=sa.String(length=320), nullable=True)
    op.add_column("customers", sa.Column("phone_normalised", sa.String(length=13), nullable=True))
    op.create_index(
        "uq_customers_phone_normalised",
        "customers",
        ["phone_normalised"],
        unique=True,
        postgresql_where=sa.text("phone_normalised IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_customers_phone_normalised", table_name="customers")
    op.drop_column("customers", "phone_normalised")
    # The column was NOT NULL before: give customers without an email a clearly fake one.
    op.execute("UPDATE customers SET email = 'unknown-' || id || '@invalid.example' WHERE email IS NULL")
    op.alter_column("customers", "email", existing_type=sa.String(length=320), nullable=False)

    op.drop_constraint("order_sales_channel_known", "orders", type_="check")
    op.drop_column("orders", "sales_channel")
