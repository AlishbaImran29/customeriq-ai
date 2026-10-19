"""Where an order came from: one of five fixed channels.

Orders carry a free-text `channel` from the imported file ("Shopify (web)", "insta dm", ...).
`sales_channel` is the clean version used for filters and charts. Anything not recognised is
"other"; it is never guessed into a wrong channel.
"""

import re

CHANNELS = ("instagram", "whatsapp", "facebook", "website", "other")
DEFAULT_CHANNEL = "other"

# Checked in this order. Short tokens must be whole words so that "wa" does not match "Swan".
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("instagram", re.compile(r"insta|\big\b", re.I)),
    ("whatsapp", re.compile(r"whats\s*app|\bwa\b", re.I)),
    ("facebook", re.compile(r"facebook|\bfb\b|\bface\s*book\b", re.I)),
    ("website", re.compile(r"web|shopify|woocommerce|magento|online|\bsite\b", re.I)),
)


def normalise_channel(text: str | None) -> str:
    """One of `CHANNELS` for any channel text; "other" when blank or not recognised."""
    if not text or not text.strip():
        return DEFAULT_CHANNEL
    for channel, pattern in _RULES:
        if pattern.search(text):
            return channel
    return DEFAULT_CHANNEL
