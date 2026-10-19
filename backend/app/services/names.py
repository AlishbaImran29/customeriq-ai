"""One spelling for each courier and each city.

Sellers write the same courier many ways ("TCS", "tcs ", "T.C.S") and the same city many ways
("Isb", "Islamabad"). A scorecard that counted them as different couriers or cities would split
the numbers into pieces too small to mean anything, so every name is turned into one standard name.

The lists are plain JSON files the seller can edit (app/data/courier_names.json and
city_names.json). A name that is NOT in the lists is never guessed: it is kept as typed (tidied up)
and reported as a NEW name, so the seller can add the spelling to the list.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.services.pk_cities import CITIES

DATA = Path(__file__).resolve().parents[1] / "data"


@dataclass(frozen=True)
class Name:
    name: str       # the standard name
    known: bool     # False when the name is not in the list (kept as typed, tidied up)
    raw: str        # exactly what was written


class NameMappingError(ValueError):
    """The list has a mistake (for example one spelling given to two different names)."""


def _key(text: str) -> str:
    """Only letters and digits, lower case: "T.C.S", "t c s" and "TCS" all become "tcs"."""
    return re.sub(r"[^a-z0-9&]", "", text.lower().replace(" and ", "&"))


def _tidy(text: str) -> str:
    """An unknown name, cleaned: extra spaces removed and each word capitalised (letters-only words
    that are all capitals, such as "DHL", stay as they are)."""
    words = re.sub(r"\s+", " ", text.strip()).split(" ")
    return " ".join(w if (w.isupper() and len(w) <= 4) else w[:1].upper() + w[1:].lower() for w in words)


class Normaliser:
    """Looks a name up in a mapping of standard name -> other spellings."""

    def __init__(self, mapping: dict[str, list[str]], extra_names: tuple[str, ...] = ()):
        self._lookup: dict[str, str] = {}
        for standard in [*mapping, *extra_names]:
            self._add(standard, standard)
        for standard, others in mapping.items():
            for other in others:
                self._add(other, standard)

    def _add(self, spelling: str, standard: str) -> None:
        key = _key(spelling)
        if not key:
            raise NameMappingError("A name in the list is empty.")
        known = self._lookup.get(key)
        if known is not None and known != standard:
            raise NameMappingError(f'The spelling "{spelling}" is given to both "{known}" and "{standard}".')
        self._lookup[key] = standard

    def normalise(self, raw: str | None) -> Name | None:
        """The standard name for `raw`, or None when it is blank."""
        if raw is None or not str(raw).strip():
            return None
        text = str(raw).strip()
        standard = self._lookup.get(_key(text))
        if standard is not None:
            return Name(standard, True, text)
        return Name(_tidy(text), False, text)

    @property
    def names(self) -> list[str]:
        return sorted(set(self._lookup.values()))


def _load(file: str, section: str) -> dict[str, list[str]]:
    data = json.loads((DATA / file).read_text(encoding="utf-8"))
    return {k: list(v) for k, v in data[section].items()}


def load_couriers(path: Path | None = None) -> Normaliser:
    if path is None:
        return Normaliser(_load("courier_names.json", "couriers"))
    return Normaliser({k: list(v) for k, v in json.loads(path.read_text(encoding="utf-8"))["couriers"].items()})


def load_cities(path: Path | None = None) -> Normaliser:
    """The cities of pk_cities.py plus the extra spellings of city_names.json."""
    if path is None:
        mapping = _load("city_names.json", "cities")
    else:
        mapping = {k: list(v) for k, v in json.loads(path.read_text(encoding="utf-8"))["cities"].items()}
    return Normaliser(mapping, extra_names=CITIES)


# The two lists in use. Edit the JSON files and restart the app to change them.
COURIERS = load_couriers()
CITY_NAMES = load_cities()


def normalise_courier(raw: str | None) -> Name | None:
    return COURIERS.normalise(raw)


def normalise_city(raw: str | None) -> Name | None:
    return CITY_NAMES.normalise(raw)
