"""When a message may go out, and how many a customer may get. Pure functions: no database, easy to test.

QUIET HOURS (default 21:00 to 10:00, Asia/Karachi). In that window nothing is sent: the message waits in the
queue until the window closes. One exception, set by the order-status feature: the "out for delivery" message
may go out from 08:00, because the customer should know before the rider arrives.

WEEKLY CAP. A customer may receive at most `cap` MARKETING messages in any rolling 7 days (the default is 2).
"Rolling" means: look back 7 days from now, not from the start of a calendar week, which is stricter and
cannot be gamed by sending 2 on Sunday and 2 on Monday. Order updates (utility) are not capped.
"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EARLY_EVENTS = {"order_out_for_delivery"}        # allowed from 08:00 instead of from the end of quiet hours
EARLY_OPEN = time(8, 0)
CAP_WINDOW_DAYS = 7


def zone(name: str):
    """The time zone. Pakistan has no daylight saving, so a fixed +5 hours is a safe fallback where the zone
    database is not installed (some Windows machines)."""
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=5)) if name == "Asia/Karachi" else timezone.utc


def _window(quiet_start: time, quiet_end: time, event: str | None) -> tuple[time, time]:
    """(opens, closes): messages may be sent from `opens` until `closes`, local time."""
    opens = EARLY_OPEN if (event in EARLY_EVENTS and EARLY_OPEN < quiet_end) else quiet_end
    return opens, quiet_start


def is_allowed(local: datetime, quiet_start: time, quiet_end: time, event: str | None = None) -> bool:
    """True when a message may be sent at this local time."""
    opens, closes = _window(quiet_start, quiet_end, event)
    now = local.time()
    if opens <= closes:                                   # a normal day window, e.g. 10:00 to 21:00
        return opens <= now < closes
    return now >= opens or now < closes                   # a window that crosses midnight (not the default)


def next_allowed(now_utc: datetime, tz_name: str, quiet_start: time, quiet_end: time, event: str | None = None) -> datetime:
    """The first moment (UTC) from `now_utc` when sending is allowed: now, or the next time the window opens."""
    tz = zone(tz_name)
    local = now_utc.astimezone(tz)
    if is_allowed(local, quiet_start, quiet_end, event):
        return now_utc
    opens, _ = _window(quiet_start, quiet_end, event)
    candidate = local.replace(hour=opens.hour, minute=opens.minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def cap_allows(recent_marketing_count: int, cap: int) -> bool:
    """True when one more marketing message is within the weekly cap. A cap of 0 means no marketing at all."""
    return recent_marketing_count < cap
