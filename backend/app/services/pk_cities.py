"""Pakistani city names, for spotting a city in a chat message.

Matching is by whole word and ignores capitals. A few common short forms map to the full name.
The list is long but not complete: an order with an unknown city is still found, the seller just
types the city in the review screen.
"""

import re

CITIES = (
    "Karachi", "Lahore", "Islamabad", "Rawalpindi", "Faisalabad", "Multan", "Peshawar", "Quetta",
    "Hyderabad", "Sialkot", "Gujranwala", "Bahawalpur", "Sargodha", "Sukkur", "Larkana", "Mardan",
    "Abbottabad", "Gujrat", "Sahiwal", "Rahim Yar Khan", "Sheikhupura", "Jhang", "Dera Ghazi Khan",
    "Mirpur", "Muzaffarabad", "Okara", "Kasur", "Mingora", "Nawabshah", "Mirpurkhas", "Chiniot",
    "Hafizabad", "Sadiqabad", "Burewala", "Jacobabad", "Shikarpur", "Khuzdar", "Gwadar", "Turbat",
    "Kohat", "Mansehra", "Swabi", "Charsadda", "Nowshera", "Attock", "Jhelum", "Wah Cantt", "Taxila",
    "Mandi Bahauddin", "Narowal", "Khanewal", "Vehari", "Layyah", "Muzaffargarh", "Bhakkar",
    "Lodhran", "Pakpattan", "Toba Tek Singh", "Gojra", "Dadu", "Thatta", "Ghotki", "Kotri",
    "Bannu", "Chakwal", "Daska", "Kamoke", "Sambrial", "Wazirabad", "Rawalakot", "Gilgit", "Skardu",
)
# Short forms people actually type.
ALIASES = {"pindi": "Rawalpindi", "isb": "Islamabad", "lhr": "Lahore", "khi": "Karachi"}

_NAMES = {c.lower(): c for c in CITIES} | ALIASES
# Longest names first, so "Dera Ghazi Khan" wins over a shorter name inside it.
_PATTERN = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(n).replace(r"\ ", r"\s+") for n in sorted(_NAMES, key=len, reverse=True)) + r")(?![A-Za-z])",
    re.IGNORECASE,
)


def find_cities(text: str) -> list[str]:
    """The cities named in `text`, in the order they appear (each at most once)."""
    found: list[str] = []
    for match in _PATTERN.finditer(text):
        name = _NAMES[re.sub(r"\s+", " ", match.group(1).lower())]
        if name not in found:
            found.append(name)
    return found
