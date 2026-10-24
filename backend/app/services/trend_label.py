"""Is a Google Trends curve rising, stable or falling? One simple rule, written here so it can be explained.

RULE: compare the average of the LAST 4 WEEKS with the average of the 8 WEEKS BEFORE THEM.
    ratio = recent average / earlier average
    ratio >= 1.15  -> "rising"      (at least 15% higher lately)
    ratio <= 0.85  -> "falling"     (at least 15% lower lately)
    otherwise      -> "stable"
Weeks are counted in days (28 and 56 days before the last date in the file), so daily and weekly exports
both work. A monthly export has too few points inside 4 weeks, so it gets no label.

This DESCRIBES the past in the file. It is not a forecast and does not claim the trend will continue.
Project rule 2: with too little data there is no label, only "Not enough data yet".
"""

from datetime import date, timedelta

RECENT_DAYS = 28
EARLIER_DAYS = 56
RISING_AT = 1.15
FALLING_AT = 0.85
MIN_SPAN_DAYS = RECENT_DAYS + EARLIER_DAYS - 1     # the file must cover both windows
MIN_RECENT_POINTS = 3                               # weekly data gives 4; allow one missing week
MIN_EARLIER_POINTS = 6                              # weekly data gives 8


def label_trend(points: list[tuple[date, float]]) -> tuple[str | None, float | None]:
    """(label, ratio) or (None, None) when there is not enough data to say."""
    if len(points) < MIN_RECENT_POINTS + MIN_EARLIER_POINTS:
        return None, None
    points = sorted(points)
    last = points[-1][0]
    if (last - points[0][0]).days < MIN_SPAN_DAYS - 7:       # a week of slack for a partly filled first week
        return None, None
    recent_start = last - timedelta(days=RECENT_DAYS - 1)
    earlier_start = recent_start - timedelta(days=EARLIER_DAYS)
    recent = [v for d, v in points if d >= recent_start]
    earlier = [v for d, v in points if earlier_start <= d < recent_start]
    if len(recent) < MIN_RECENT_POINTS or len(earlier) < MIN_EARLIER_POINTS:
        return None, None
    earlier_average = sum(earlier) / len(earlier)
    if earlier_average <= 0:
        return None, None
    ratio = (sum(recent) / len(recent)) / earlier_average
    if ratio >= RISING_AT:
        return "rising", round(ratio, 3)
    if ratio <= FALLING_AT:
        return "falling", round(ratio, 3)
    return "stable", round(ratio, 3)
