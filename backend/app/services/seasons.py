"""Reads the season date tables (app/data/seasons.json) into plain windows.

A window is the stretch of days the Season Forecast adds up (for example the 14 days up to Eid ul Adha).
Mistakes in the file stop the app with a clear message, because a wrong date silently gives wrong advice.
"""

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

SEASONS_FILE = Path(__file__).resolve().parents[1] / "data" / "seasons.json"


class SeasonConfigError(ValueError):
    """The seasons file has a mistake (bad date, end before start, missing field)."""


@dataclass(frozen=True)
class Window:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


@dataclass(frozen=True)
class Season:
    id: str
    name: str
    windows: dict[int, Window]       # year -> window


def _date(text: str, where: str) -> date:
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError) as error:
        raise SeasonConfigError(f"{where}: '{text}' is not a date like 2026-05-27.") from error


def parse_seasons(config: dict) -> list[Season]:
    seasons, seen = [], set()
    for entry in config.get("seasons", []):
        try:
            sid, name, kind = entry["id"], entry["name"], entry["kind"]
        except KeyError as error:
            raise SeasonConfigError(f"A season is missing '{error.args[0]}'.") from error
        if sid in seen:
            raise SeasonConfigError(f"Season id '{sid}' is used twice.")
        seen.add(sid)
        windows: dict[int, Window] = {}
        if kind == "moving":
            lead = entry.get("lead_days")
            if not isinstance(lead, int) or not 1 <= lead <= 120:
                raise SeasonConfigError(f"{sid}: lead_days must be a whole number from 1 to 120.")
            for year, day in entry.get("dates", {}).items():
                festival = _date(day, f"{sid} {year}")
                if str(festival.year) != str(year):
                    raise SeasonConfigError(f"{sid}: the date for {year} is in {festival.year}.")
                windows[int(year)] = Window(festival - timedelta(days=lead - 1), festival)
        elif kind == "fixed":
            for year in entry.get("years", []):
                start, end = _date(f"{year}-{entry.get('start')}", f"{sid} start"), _date(f"{year}-{entry.get('end')}", f"{sid} end")
                if end < start:
                    raise SeasonConfigError(f"{sid}: the end is before the start.")
                windows[int(year)] = Window(start, end)
        else:
            raise SeasonConfigError(f"{sid}: kind must be 'moving' or 'fixed'.")
        if not windows:
            raise SeasonConfigError(f"{sid}: no years are listed.")
        seasons.append(Season(sid, name, dict(sorted(windows.items()))))
    return seasons


def load_seasons(path: Path | None = None) -> list[Season]:
    return parse_seasons(json.loads((path or SEASONS_FILE).read_text(encoding="utf-8")))


SEASONS = load_seasons()
