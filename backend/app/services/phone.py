"""Pakistani mobile numbers, in ONE format: +92 followed by 10 digits, e.g. +923001234567.

Sellers type the same number many ways (0300-1234567, 3001234567, +92 300 1234567, 0092...).
Turning them into one format is what lets the app recognise a returning customer by phone
number: the normalised number is the key used to merge repeat customers.

Only Pakistani MOBILE numbers are accepted: after the country code comes a 3 and nine more
digits (3XX XXXXXXX). Landlines, numbers of other countries and anything that is not a number
give None, never a guess. (`whatsapp.py` handles numbers of any country for the WhatsApp link.)
"""

import re

COUNTRY_CODE = "92"
NOT_A_PK_MOBILE = "Not a Pakistani mobile number. Use a format like 0300 1234567 or +92 300 1234567."

_SEPARATORS = re.compile(r"[\s\-().]")
_NORMAL = re.compile(r"^\+923\d{9}$")


def normalise_pk_phone(text: str | None) -> str | None:
    """`+923XXXXXXXXX` for a Pakistani mobile number written in any common way, else None.

    0300-1234567       -> +923001234567   (local, with the trunk 0)
    3001234567         -> +923001234567   (local, without the 0)
    +92 300 1234567    -> +923001234567
    0092 300 1234567   -> +923001234567   (00 = "international" prefix)
    923001234567       -> +923001234567   (country code without the +)
    +92 0300 1234567   -> +923001234567   (a common mistake: the 0 kept after +92)
    """
    if not text:
        return None
    cleaned = _SEPARATORS.sub("", text.strip())
    digits = cleaned[1:] if cleaned.startswith("+") else cleaned
    if not digits.isdigit():
        return None                                   # letters or other symbols: do not guess

    if cleaned.startswith("+") or digits.startswith("00"):
        national = digits[2:] if digits.startswith("00") else digits
        if not national.startswith(COUNTRY_CODE):
            return None                               # another country
        rest = national[len(COUNTRY_CODE):]
    elif digits.startswith(COUNTRY_CODE) and len(digits) >= 12:
        rest = digits[len(COUNTRY_CODE):]             # 923001234567
    elif digits.startswith("0"):
        rest = digits[1:]                             # 0300 1234567
    else:
        rest = digits                                 # 300 1234567

    if rest.startswith("0"):
        rest = rest[1:]                               # "+92 0300 ..." typed with the extra 0
    number = f"+{COUNTRY_CODE}{rest}"
    return number if _NORMAL.match(number) else None
