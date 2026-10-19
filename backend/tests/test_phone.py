"""Pakistani mobile numbers: every common way of typing one gives the same result."""

import pytest

from app.services.phone import normalise_pk_phone

SAME = "+923001234567"


@pytest.mark.parametrize(
    "typed",
    [
        "03001234567", "0300-1234567", "0300 1234567", "(0300) 123-4567", "0300.1234567",
        "3001234567", "300 1234567", "300-1234567",
        "+923001234567", "+92 300 1234567", "+92-300-1234567",
        "00923001234567", "0092 300 1234567", "0092-300-1234567",
        "923001234567", "92 300 1234567",
        "+92 0300 1234567", "+9203001234567",          # the 0 kept after +92 by mistake
        "  0300 1234567  ",
    ],
)
def test_every_common_way_of_writing_a_number_gives_the_same_result(typed):
    assert normalise_pk_phone(typed) == SAME


@pytest.mark.parametrize(
    ("typed", "expected"),
    [("0321-9876543", "+923219876543"), ("3456789012", "+923456789012"), ("+92 345 6789012", "+923456789012")],
)
def test_other_operators_keep_their_own_digits(typed, expected):
    assert normalise_pk_phone(typed) == expected


@pytest.mark.parametrize(
    "typed",
    [
        None, "", "   ", "abc", "0300-ABC4567",
        "0300123456",             # one digit short
        "030012345678",           # one digit too many
        "042 35761234",           # a Lahore landline is not a mobile number
        "+44 7911 123456",        # another country
        "+971 50 123 4567",
        "0092",                   # nothing after the country code
        "+92 200 1234567",        # mobile numbers start with 3 after +92
        "12345",
        "+",
    ],
)
def test_anything_that_is_not_a_pakistani_mobile_number_gives_none(typed):
    assert normalise_pk_phone(typed) is None


def test_the_result_is_always_plus_92_and_ten_digits():
    result = normalise_pk_phone("0300 1234567")
    assert result.startswith("+92") and len(result) == 13 and result[1:].isdigit()
