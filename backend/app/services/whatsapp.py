"""Turn a phone number from the seller's data into the digits a wa.me link needs.

`https://wa.me/<number>` wants the full international number, digits only: no +, no spaces,
and no leading zero (92300..., not 0300...). Sellers type numbers many ways, so the common ones
are accepted. When a number cannot be read safely the result is None and the app shows
"no phone number" instead of opening a chat with a wrong person.
"""

import re

from app.services import order_risk_config as config

_SEPARATORS = re.compile(r"[\s\-().]")
_MIN_DIGITS, _MAX_DIGITS = 8, 15      # the limits of an international number (E.164)


def whatsapp_number(phone: str | None) -> str | None:
    """The international digits for `phone`, or None if it cannot be read with confidence.

    +92 300 1234567   -> 923001234567      (already international)
    0092 300 1234567  -> 923001234567      (00 = "international" prefix)
    0300 1234567      -> 923001234567      (leading 0 = local number)
    300 1234567       -> 923001234567      (10 digits: the local number without its 0)
    923001234567      -> 923001234567
    """
    if not phone:
        return None
    cleaned = _SEPARATORS.sub("", phone.strip())
    plus = cleaned.startswith("+")
    digits = cleaned[1:] if plus else cleaned
    if not digits.isdigit():
        return None                                # letters or other symbols: do not guess

    code = config.WHATSAPP_DEFAULT_COUNTRY_CODE
    if plus:
        number = digits
    elif digits.startswith("00"):
        number = digits[2:]
    elif digits.startswith("0"):
        number = code + digits[1:]
    elif len(digits) == 10:
        number = code + digits
    else:
        number = digits                            # e.g. 923001234567: assume it is complete

    if number.startswith("0") or not _MIN_DIGITS <= len(number) <= _MAX_DIGITS:
        return None
    return number
