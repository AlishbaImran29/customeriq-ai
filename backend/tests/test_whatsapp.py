"""Phone numbers for the WhatsApp link: the usual ways sellers type them, and the unsafe ones."""

import pytest

from app.services import order_risk_config as config
from app.services.whatsapp import whatsapp_number


@pytest.mark.parametrize(
    "typed",
    ["+92 300 1234567", "+92-300-1234567", "0092 300 1234567", "0300 1234567", "03001234567",
     "(0300) 123-4567", "300 1234567", "923001234567", " 0300.1234567 "],
)
def test_pakistani_numbers_in_common_formats_become_the_same_digits(typed):
    assert whatsapp_number(typed) == "923001234567"


def test_numbers_from_other_countries_keep_their_own_code():
    assert whatsapp_number("+44 7911 123456") == "447911123456"
    assert whatsapp_number("+971 50 123 4567") == "971501234567"


@pytest.mark.parametrize("typed", [None, "", "   ", "abc", "0300-ABC-4567", "12345", "+0300 1234567", "0", "+" + "1" * 16])
def test_numbers_that_cannot_be_read_safely_give_none(typed):
    assert whatsapp_number(typed) is None


def test_the_default_country_code_comes_from_the_config(monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_DEFAULT_COUNTRY_CODE", "91")
    assert whatsapp_number("098765 43210") == "919876543210"
