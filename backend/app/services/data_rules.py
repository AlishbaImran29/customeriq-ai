"""Rules about how much data is enough, in ONE place.

Project rule 2: never draw a conclusion from small numbers. A courier in a city, a product in a
season, a group of any kind needs at least this many cases before the app shows a rate or a
ranking for it; below that it says "Not enough data yet". Change the number here to make the rule
stricter or looser everywhere it is used.
"""

MIN_GROUP_COUNT = 20


def enough(count: int) -> bool:
    """True when a group of `count` cases is big enough to show a rate for."""
    return count >= MIN_GROUP_COUNT


def more_needed(count: int) -> int:
    """How many more cases a group needs (0 when it already has enough)."""
    return max(0, MIN_GROUP_COUNT - count)
