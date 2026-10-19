"""Who is this customer? A phone number is the key that merges repeat customers.

A seller on WhatsApp or Instagram often has no email and no customer id: the customer is
"the person with this number". So when an order arrives with a phone number (normalised by
`phone.py`) the app first asks: does a customer with this number already exist? If yes, the
order is added to THAT customer; if not, a new customer is created. This avoids the same
person appearing twice just because they were typed as 0300-1234567 once and +92 300 1234567
another time.

Known limit: two different people who share one phone number (for example a family) become
one customer.
"""

from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer
from app.services.import_validation import OrderRow


def existing_phone_owners(db: Session, phones: set[str]) -> dict[str, str]:
    """phone_normalised -> customer_id (external id) of the customers already saved with it."""
    owners: dict[str, str] = {}
    numbers = list(phones)
    for start in range(0, len(numbers), 1000):
        batch = numbers[start : start + 1000]
        owners.update(
            db.execute(
                select(Customer.phone_normalised, Customer.external_id).where(Customer.phone_normalised.in_(batch))
            ).all()
        )
    return owners


def assign_customers_by_phone(rows: list[OrderRow], owners: dict[str, str]) -> tuple[list[OrderRow], int]:
    """Give every row with a phone number the customer id that already owns that number.

    `owners` holds numbers already saved. Within the file, the FIRST customer id seen with a
    number owns it. Returns the rows (customer ids replaced where they were merged) and how many
    rows were merged into another customer. Rows without a phone number are left as they are.
    """
    owner = dict(owners)
    result: list[OrderRow] = []
    merged = 0
    for row in rows:
        if row.phone_normalised:
            chosen = owner.setdefault(row.phone_normalised, row.customer_id)
            if chosen != row.customer_id:
                merged += 1
                row = replace(row, customer_id=chosen)
        result.append(row)
    return result, merged
