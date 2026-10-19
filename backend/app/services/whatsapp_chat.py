"""Read a WhatsApp "Export chat" text file (without media) into a list of messages.

Both Android and iPhone layouts are understood:

    18/10/2026, 9:15 pm - Ali: I need 2 suits          (Android, 12 hour; 24 hour works too)
    [18/10/2026, 21:15:03] Ali: I need 2 suits         (iPhone)

The file is handled as text in memory only. This module never writes it anywhere and never logs
any of it: a chat holds other people's private messages.

What it does NOT do: decide what is an order (see chat_orders.py).
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

DateOrder = Literal["dmy", "mdy", "ymd"]

# WhatsApp puts invisible marks and (on new versions) a narrow no-break space before "pm".
_INVISIBLE = dict.fromkeys(map(ord, "‎‏‪‫‬﻿"), None)
_SPACES = dict.fromkeys(map(ord, "   "), " ")

_DATE = r"(\d{1,4})[/.\-](\d{1,2})[/.\-](\d{1,4})"
_TIME = r"(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?\s*([APap]\.?[Mm]\.?)?"
_ANDROID = re.compile(rf"^{_DATE},?\s+{_TIME}\s+-\s+(.*)$")
_IPHONE = re.compile(rf"^\[{_DATE},?\s+{_TIME}\]\s+(.*)$")
_SENDER = re.compile(r"^([^:]{1,80}?):\s(.*)$|^([^:]{1,80}?):$")

# Lines the app writes itself (no human sender), and messages that carry no text.
_SYSTEM = re.compile(
    r"end-to-end encrypted|created group|changed (?:the )?(?:subject|this group|group)|added you|"
    r"you(?:'re| are) now an admin|joined using|left$|removed|changed their phone number|"
    r"security code changed|messages? (?:and calls )?(?:are|is) (?:now )?secured|"
    r"disappearing messages|turned (?:on|off) (?:disappearing|admin)",
    re.IGNORECASE,
)
# On an iPhone the app's own notices carry the chat name as a sender ("Hina: Messages and calls are
# end-to-end encrypted"). Only phrases that no customer would write are treated that way.
_SYSTEM_TEXT = re.compile(
    r"end-to-end encrypted|created group|changed the subject|security code changed|"
    r"you(?:'re| are) now an admin|joined using|disappearing messages|changed their phone number",
    re.IGNORECASE,
)
_MEDIA = re.compile(
    r"^(?:<media omitted>|(?:image|video|audio|sticker|document|gif|contact card|voice call|video call)"
    r"(?: omitted)?|(?:you )?deleted this message|this message was deleted|missed (?:voice|video) call|"
    r"null|waiting for this message.*)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Message:
    index: int
    when: datetime
    sender: str
    text: str


@dataclass
class ParsedChat:
    messages: list[Message] = field(default_factory=list)
    senders: list[tuple[str, int]] = field(default_factory=list)   # (name, number of messages), busiest first
    date_order: DateOrder = "dmy"
    date_order_ambiguous: bool = False       # every date fits both day-first and month-first
    system_lines: int = 0
    media_messages: int = 0
    customer_name_hint: str | None = None    # from the file name ("WhatsApp Chat with Ali.txt")
    unreadable_lines: int = 0                # looked like a message header but not a real date or time


def _clean(text: str) -> list[str]:
    return text.translate(_INVISIBLE).translate(_SPACES).splitlines()


def name_from_filename(filename: str | None) -> str | None:
    """The other person's name in "WhatsApp Chat with Ali Khan.txt" or "WhatsApp Chat - Ali Khan.txt"."""
    if not filename:
        return None
    base = re.sub(r"\.(txt|zip)$", "", filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1], flags=re.IGNORECASE)
    match = re.match(r"^WhatsApp Chat(?: with| -|\s*–)\s+(.+?)(?:\s*\(\d+\))?$", base.strip(), re.IGNORECASE)
    return match.group(1).strip() if match else None


def _split(rest: str) -> tuple[str | None, str]:
    """(sender, text) of the part after the time, or (None, text) for a system line."""
    if _SYSTEM.search(rest) and not _SENDER.match(rest):
        return None, rest
    match = _SENDER.match(rest)
    if not match:
        return None, rest
    sender = (match.group(1) or match.group(3)).strip()
    text = (match.group(2) if match.group(1) is not None else "").strip()
    return sender, text


def _headers(lines: list[str]):
    """Yield (line number, numbers of the date, time parts, rest) for every line that starts a message."""
    for number, line in enumerate(lines):
        for pattern in (_ANDROID, _IPHONE):
            match = pattern.match(line.strip())
            if match:
                yield number, match.groups()
                break


def detect_date_order(first_numbers: list[tuple[int, int, int]]) -> tuple[DateOrder, bool]:
    """Day first or month first? Decided from the dates themselves: a first number above 12 can only
    be a day, a second number above 12 can only be a day. When every date is 12 or below it is a
    guess (day first, as in Pakistan) and the caller is told it is ambiguous."""
    if any(a > 31 for a, _, _ in first_numbers):
        return "ymd", False
    first_big = any(a > 12 for a, _, _ in first_numbers)
    second_big = any(b > 12 for _, b, _ in first_numbers)
    if first_big and not second_big:
        return "dmy", False
    if second_big and not first_big:
        return "mdy", False
    return "dmy", not (first_big and second_big)


def _to_datetime(numbers: tuple[int, int, int], time_parts: tuple, order: DateOrder) -> datetime | None:
    a, b, c = numbers
    day, month, year = {"dmy": (a, b, c), "mdy": (b, a, c), "ymd": (c, b, a)}[order]
    if year < 100:
        year += 2000
    hour, minute, second, meridiem = int(time_parts[0]), int(time_parts[1]), int(time_parts[2] or 0), time_parts[3]
    if meridiem:
        pm = meridiem.lower().startswith("p")
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if pm else 0)
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def parse_chat(text: str, filename: str | None = None, date_order: DateOrder | None = None) -> ParsedChat:
    """Messages in time order, with system lines and media placeholders left out.

    `date_order` forces day-first or month-first (used when the dates are ambiguous and the seller
    has chosen). Lines before the first message, and lines that are not messages, are ignored; a line
    that does not start a message is a continuation of the message above it.
    """
    lines = _clean(text)
    starts = list(_headers(lines))
    chat = ParsedChat(customer_name_hint=name_from_filename(filename))
    if not starts:
        return chat

    numbers = [(int(g[0]), int(g[1]), int(g[2])) for _, g in starts]
    detected, ambiguous = detect_date_order(numbers)
    chat.date_order = date_order or detected
    chat.date_order_ambiguous = ambiguous and date_order is None

    counts: Counter[str] = Counter()
    for position, (line_number, groups) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        rest = groups[-1].strip()
        # Following lines up to the next header belong to this message.
        extra = [ln for ln in lines[line_number + 1 : end]]
        sender, body = _split(rest)
        full = "\n".join([body, *extra]).strip()
        when = _to_datetime(numbers[position], groups[3:7], chat.date_order)
        if when is None:
            chat.unreadable_lines += 1
            continue
        if sender is None or _SYSTEM_TEXT.search(full):
            chat.system_lines += 1
            continue
        if not full or _MEDIA.match(full):
            chat.media_messages += 1
            continue
        chat.messages.append(Message(len(chat.messages), when, sender, full))
        counts[sender] += 1

    chat.messages.sort(key=lambda m: (m.when, m.index))
    chat.senders = counts.most_common()
    return chat
