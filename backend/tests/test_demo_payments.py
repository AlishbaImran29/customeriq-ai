"""The made-up demo payments. The shipments used here are invented too."""

from datetime import date, timedelta
from importlib import util
from pathlib import Path

from app.services.import_files import parse_file
from app.services.payment_import import validate_payments

ROOT = Path(__file__).resolve().parents[2]
spec = util.spec_from_file_location("generate_demo_payments", ROOT / "backend" / "scripts" / "generate_demo_payments.py")
demo = util.module_from_spec(spec)
spec.loader.exec_module(demo)


def made_up_shipments():
    rows = []
    for i in range(300):
        delivered = date(2026, 1, 1) + timedelta(days=i % 150)
        rows.append({
            "courier_name": ["TCS", "Leopards", "Trax", "PostEx"][i % 4], "status": "delivered", "cod_amount": "1000.00",
            "delivered_or_returned_date": delivered.isoformat(),
        })
    return rows


def test_rows_are_always_synthetic_and_repeatable():
    rows = demo.generate(made_up_shipments())
    assert rows and {r["data_source"] for r in rows} == {"demo (synthetic)"}
    assert demo.generate(made_up_shipments()) == rows


def test_the_recent_weeks_are_left_unpaid():
    rows = demo.generate(made_up_shipments())
    assert max(r["payment_date"] for r in rows) < "2026-05-30"        # data ends 2026-05-30; the last weeks stay open


def test_every_generated_row_passes_the_real_payment_validation():
    import csv
    import io

    rows = demo.generate(made_up_shipments())
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=demo.COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    result = validate_payments(parse_file(buffer.getvalue().encode(), "csv"))
    assert result.errors == [] and len(result.rows) == len(rows)
