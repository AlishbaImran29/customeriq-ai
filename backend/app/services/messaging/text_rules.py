"""Reading what a customer typed back: STOP, YES and NO, in English, Roman Urdu and Urdu.

STOP must always work (project rule 2), so the rules are strict about not MISSING a stop and careful about not
stopping someone by accident: a message counts as STOP only when the WHOLE message is a stop phrase, or it
starts with "stop" or "unsubscribe" and is short (at most 3 words). "Please don't stop the delivery" is not a stop.
The word lists are plain data below: add a phrase there and it works everywhere.
"""

import re
import unicodedata

STOP_PHRASES = {
    # English
    "stop", "stop all", "stop messages", "stop messaging", "unsubscribe", "unsub", "cancel", "end", "quit", "opt out", "optout",
    "remove me", "do not message", "dont message", "no more messages",
    # Roman Urdu
    "band karo", "band kro", "band kar do", "band kardo", "band karein", "band karen", "bnd karo", "message band karo", "msg band karo",
    "mat bhejo", "mat bhejain", "mat bhejen", "na bhejo", "na bhejain", "bas karo", "bus karo", "rok do", "roko",
    # Urdu
    "بند کرو", "بند کریں", "بند کر دو", "بند کردو", "پیغام بند کرو", "پیغامات بند کریں", "مت بھیجو", "مت بھیجیں", "نہ بھیجیں", "بس کرو", "روک دو",
}
STOP_FIRST_WORDS = {"stop", "unsubscribe", "stopp"}
YES_WORDS = {"yes", "y", "yeah", "yep", "ok", "okay", "sure", "haan", "han", "haa", "ji haan", "ji han", "jee haan", "ہاں", "ہان", "جی ہاں", "جی", "ٹھیک ہے"}
NO_WORDS = {"no", "n", "nope", "nahi", "nahin", "nai", "na", "ji nahi", "ji nahin", "نہیں", "نا", "جی نہیں"}

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)


def normalise(text: str | None) -> str:
    """Lower case, no accents or punctuation, single spaces: "  STOP!! " -> "stop"."""
    text = unicodedata.normalize("NFKC", text or "").casefold()
    text = _PUNCTUATION.sub(" ", text.replace("_", " "))
    return " ".join(text.split())


def is_stop(text: str | None) -> bool:
    words = normalise(text)
    if not words:
        return False
    if words in STOP_PHRASES:
        return True
    tokens = words.split()
    return tokens[0] in STOP_FIRST_WORDS and len(tokens) <= 3


def yes_or_no(text: str | None) -> str | None:
    """"yes", "no" or None when the text is not a clear answer."""
    words = normalise(text)
    if words in YES_WORDS:
        return "yes"
    if words in NO_WORDS:
        return "no"
    return None
