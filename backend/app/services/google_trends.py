"""Read a Google Trends CSV that the seller exported by hand from trends.google.com.

WHY A FILE AND NOT AN AUTOMATIC FETCH: Google Trends has no free official API for this data, and
scraping Google is not allowed. So the seller downloads the CSV themselves (Pakistan region) and
uploads it. The app only ever reads what the seller gives it.

Two export formats are understood (and a file may hold both):

1. "Interest over time": some lines Google adds first ("Category: All categories", a blank line),
   then a header like   Week,sneakers: (Pakistan)   (or Day / Month, and possibly several keywords),
   then one row per period:  2026-01-04,45.   Values run 0-100 (100 = the most popular moment in the
   file), and Google writes "<1" for a value below 1.
2. "Related queries": blocks that start with a TOP or RISING line, a header line, and rows like
   air jordan,100   or   nike shoes,Breakout   or   cheap shoes,+250%.

Nothing here guesses: a file that is neither format is rejected with a plain message.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date

from app.core.errors import ApiError

MAX_BYTES = 2 * 1024 * 1024
MAX_POINTS = 5000
MAX_RELATED = 100
MAX_KEYWORD = 120

_KEYWORD_HEADER = re.compile(r"^(?P<keyword>.+?):\s*\((?P<region>[^)]*)\)\s*$")
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_MONTH = re.compile(r"^\d{4}-\d{2}$")
_PERIOD_HEADERS = {"day": "day", "week": "week", "month": "month", "time": "day"}


@dataclass
class TrendSeries:
    keyword: str
    region: str | None
    granularity: str                              # "day", "week" or "month"
    points: list[tuple[date, float]] = field(default_factory=list)


@dataclass
class RelatedQuery:
    query: str
    value: str                                    # "100", "Breakout" or "+250%", as Google wrote it
    kind: str                                     # "top" or "rising"


@dataclass
class ParsedTrends:
    series: list[TrendSeries] = field(default_factory=list)
    related: list[RelatedQuery] = field(default_factory=list)


def _decode(content: bytes) -> str:
    """Google's files are UTF-8 (sometimes with a BOM) or, in some browsers, UTF-16."""
    if len(content) > MAX_BYTES:
        raise ApiError(413, "file_too_large", "The file is larger than 2 MB. A Google Trends export is much smaller than that.")
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ApiError(422, "not_a_trends_file", "This does not look like a Google Trends CSV (it is not text).")


def _value(text: str) -> float | None:
    text = text.strip()
    if text == "<1":
        return 0.5                                 # Google rounds anything below 1 to "<1"
    try:
        number = float(text)
    except ValueError:
        return None
    return number if 0 <= number <= 100 else None


def _day(text: str, granularity: str) -> date | None:
    text = text.strip()
    try:
        if granularity == "month" and _ISO_MONTH.match(text):
            return date.fromisoformat(text + "-01")
        if _ISO_DAY.match(text):
            return date.fromisoformat(text)
    except ValueError:
        return None
    return None


def _parse_interest(rows: list[list[str]], start: int) -> list[TrendSeries]:
    header = rows[start]
    granularity = _PERIOD_HEADERS[header[0].strip().lower()]
    series = []
    for column, name in enumerate(header[1:], start=1):
        match = _KEYWORD_HEADER.match(name.strip())
        keyword = (match.group("keyword") if match else name).strip()[:MAX_KEYWORD]
        if keyword:
            series.append(TrendSeries(keyword, match.group("region").strip() if match else None, granularity))
    for row in rows[start + 1:]:
        if not row or not any(c.strip() for c in row):
            break                                   # a blank line ends the table (related queries may follow)
        when = _day(row[0], granularity)
        if when is None:
            break
        for column, one in enumerate(series, start=1):
            value = _value(row[column]) if column < len(row) else None
            if value is not None:
                one.points.append((when, value))
    return [s for s in series if s.points]


def _parse_related(rows: list[list[str]]) -> list[RelatedQuery]:
    related: list[RelatedQuery] = []
    kind: str | None = None
    for row in rows:
        first = row[0].strip() if row else ""
        if first.upper() in ("TOP", "RISING"):
            kind = first.lower()
            continue
        if kind is None or not first or len(row) < 2:
            continue                                # before the first TOP / RISING line, or a blank line
        if first.lower() in ("query", "topic") or not row[1].strip():
            continue                                # the column header line
        related.append(RelatedQuery(first[:MAX_KEYWORD], row[1].strip()[:30], kind))
    return related[:MAX_RELATED]


def parse_google_trends(content: bytes) -> ParsedTrends:
    """Parse an uploaded file. Raises a plain ApiError when it is not a Google Trends export."""
    text = _decode(content)
    rows = [row for row in csv.reader(io.StringIO(text))]
    result = ParsedTrends()
    for index, row in enumerate(rows):
        if row and row[0].strip().lower() in _PERIOD_HEADERS and len(row) >= 2:
            result.series = _parse_interest(rows, index)
            break
    if any(row and row[0].strip().upper() in ("TOP", "RISING") for row in rows):
        result.related = _parse_related(rows)
    if not result.series and not result.related:
        raise ApiError(
            422, "not_a_trends_file",
            "This does not look like a Google Trends export. Download \"interest over time\" or \"related queries\" "
            "from trends.google.com with the download arrow, and upload that file.",
        )
    for one in result.series:
        if len(one.points) > MAX_POINTS:
            raise ApiError(422, "trends_too_long", "The file has too many rows for one trend.")
    return result
