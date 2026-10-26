"""A small "no more than N times in M seconds" limiter, kept in memory.

Used to stop one account from running up the AI bill (every AI call costs money).
Honest limit: on a serverless host each running copy of the API has its own memory, so the limit
is per copy, not global. It still stops a loop or a runaway script; a global limit would need a
database table.
"""

import threading
import time
from collections import defaultdict, deque

from app.core.errors import ApiError

_lock = threading.Lock()
_events: dict[str, deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    with _lock:
        _events.clear()


def check_rate_limit(key: str, *, limit: int, window_seconds: int, what: str) -> None:
    """Record one use of `key`; raise a friendly 429 when it is used more than `limit` times in the window."""
    now = time.monotonic()
    with _lock:
        recent = _events[key]
        while recent and now - recent[0] > window_seconds:
            recent.popleft()
        if len(recent) >= limit:
            wait = max(1, int(window_seconds - (now - recent[0])))
            raise ApiError(
                429, "rate_limited",
                f"You have asked {what} too many times in a short while. Please wait about {max(1, wait // 60)} minute(s) and try again.",
            )
        recent.append(now)
        if len(_events) > 10_000:                      # never let the table grow without end
            for stale in [k for k, v in _events.items() if not v or now - v[-1] > window_seconds]:
                _events.pop(stale, None)
