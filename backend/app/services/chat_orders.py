"""Find the messages in a chat that look like orders, with simple rules (no AI, no paid service).

Every step is a rule you can read and explain:
1. Each message is searched for facts: an amount, a phone number, a city, order words.
2. Messages close together in time (15 minutes or less) are one conversation, because a customer
   often writes "I want this" first and sends the address and phone number a minute later.
3. A conversation that looks like an order becomes a CANDIDATE, with a label saying what was
   found, so the seller knows what to check. Nothing is saved from here: the seller reviews
   every candidate (see api/v1/whatsapp_import.py).

What is NOT guessed: the products. They are typed by the seller in the review screen, next to the
original messages. Guessing product names from free text would be wrong too often.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.services.phone import normalise_pk_phone
from app.services.pk_cities import find_cities
from app.services.whatsapp_chat import Message

CONVERSATION_GAP = timedelta(minutes=15)
MIN_AMOUNT = Decimal(10)               # "Rs 5" is a typo or a number of items, not an order amount
MAX_AMOUNT = Decimal("9999999.99")
MAX_SOURCE_MESSAGES = 8                # messages shown next to a candidate
MAX_SOURCE_TEXT = 400

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")   # Urdu and Arabic digits

# --- phone numbers: a Pakistani mobile number in any usual spelling -------------------------------
_PHONE = re.compile(r"(?<!\d)(?:\+\s*92|0092|92|0)?[\s\-]?3\d{2}[\s\-]?(?:\d{7}|\d{3}[\s\-]?\d{4})(?!\d)")

# --- amounts: Rs 2500, Rs.2,500, PKR 2500, 2500/-, 2500 rupay, 2500 rs ---------------------------
_NUMBER = r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?"
_AMOUNT = re.compile(
    rf"(?:\b(?:rs|pkr)(?![A-Za-z])\.?\s*{_NUMBER})"                 # Rs 2500, Rs.2,500, rs2500
    rf"|(?:\b(?:rupees?|rupay|rupaye)\b\.?\s*{_NUMBER})"           # rupay 2500
    rf"|(?:{_NUMBER}\s*/-)"                                         # 2500/-
    rf"|(?:{_NUMBER}\s*(?:rs|pkr|rupees?|rupay|rupaye)\b)",         # 2500 rupay
    re.IGNORECASE,
)
_TOTAL_BEFORE = re.compile(r"(?:total|kul|bill|payable|sum|jama)\W{0,25}$", re.IGNORECASE)

# --- order words (English and Roman Urdu) ---------------------------------------------------------
_STRONG = re.compile(
    r"\border(?:s|ed|ing)?\b|\bconfirm(?:ed)?\b|\bbook(?:ed|ing)?\b|\bcod\b|cash\s+on\s+deliver|"
    r"\bbhej\s*(?:do|dein|den|dain|dijiye|dijye)\b|\bbhejo\b|\bbhijwa\s*(?:do|dein|dain)\b|"
    r"\bchah?(?:i|ie|iye|yeh?)\b|\bchaiye\b|آرڈر|چاہیے|کنفرم|بھیج\s*دو",
    re.IGNORECASE,
)
_WEAK = re.compile(r"\bkit(?:ne|nay|ni)\s+k[ai]\b|\baddress\b|\bdeliver(?:y|ed)?\b|\bprice\b|پتہ", re.IGNORECASE)
_COD = re.compile(r"\bcod\b|cash\s+on\s+deliver", re.IGNORECASE)
_PREPAID = re.compile(
    r"\badvance\b|\beasy\s*paisa\b|\bjazz\s*cash\b|\bbank\s+transfer\b|\btransferred\b|"
    r"\bpayment\s+(?:done|kar\s*di|sent)\b|\bpaid\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Facts:
    """What one message says. `amounts` are (value, looks like a total)."""

    amounts: tuple[tuple[Decimal, bool], ...] = ()
    phones: tuple[str, ...] = ()
    cities: tuple[str, ...] = ()
    strong: bool = False
    weak: bool = False
    cod: bool = False
    prepaid: bool = False

    @property
    def any(self) -> bool:
        return bool(self.amounts or self.phones or self.cities or self.strong or self.weak)


def message_facts(text: str) -> Facts:
    """Look for amounts, phone numbers, a city and order words in one message."""
    text = text.translate(_DIGITS)
    phones: list[str] = []
    for match in _PHONE.finditer(text):
        number = normalise_pk_phone(match.group(0))
        if number and number not in phones:
            phones.append(number)
    # Take the phone numbers out before looking for amounts, so a number is never both.
    without_phones = _PHONE.sub(" ", text)

    amounts: list[tuple[Decimal, bool]] = []
    for match in _AMOUNT.finditer(without_phones):
        raw = next(g for g in match.groups() if g)
        value = Decimal(raw.replace(",", ""))
        if MIN_AMOUNT <= value <= MAX_AMOUNT:
            amounts.append((value, bool(_TOTAL_BEFORE.search(without_phones[: match.start()]))))
    return Facts(
        amounts=tuple(amounts),
        phones=tuple(phones),
        cities=tuple(find_cities(text)),
        strong=bool(_STRONG.search(text)),
        weak=bool(_WEAK.search(text)),
        cod=bool(_COD.search(text)),
        prepaid=bool(_PREPAID.search(text)),
    )


@dataclass(frozen=True)
class SourceMessage:
    sender: str
    when: datetime
    text: str


@dataclass
class Candidate:
    id: int
    customer_name: str
    phone: str | None
    city: str | None
    amount: Decimal | None
    other_amounts: list[Decimal]
    payment_type: str | None            # "cod", "prepaid" or None when the chat does not say
    order_date: date
    order_time: datetime                # when the first message of the order was sent
    confidence: str                     # "high" | "medium" | "low"
    confidence_label: str
    found: dict[str, bool] = field(default_factory=dict)
    messages: list[SourceMessage] = field(default_factory=list)


def _confidence(has_amount: bool, has_phone: bool) -> tuple[str, str]:
    if has_amount and has_phone:
        return "high", "Amount and phone found"
    if has_amount:
        return "medium", "Only amount found"
    if has_phone:
        return "medium", "Only phone found"
    return "low", "Only keyword found"


def _phone_like_name(sender: str) -> str | None:
    """Unsaved contacts show up as their number: "+92 300 1234567"."""
    return normalise_pk_phone(sender)


def _conversations(messages: list[Message], facts: list[Facts]) -> list[list[int]]:
    """Indexes of messages grouped into conversations (15 minutes or less between messages). A
    message with a different phone number, after the conversation already has an amount and a
    number, starts a new one: it is another customer's order."""
    groups: list[list[int]] = []
    current: list[int] = []
    phones: set[str] = set()
    has_amount = False
    last: datetime | None = None
    for i, message in enumerate(messages):
        f = facts[i]
        if current and last is not None:
            another_customer = bool(f.phones) and bool(phones) and has_amount and not (set(f.phones) & phones)
            if message.when - last > CONVERSATION_GAP or another_customer:
                groups.append(current)
                current, phones, has_amount = [], set(), False
        current.append(i)
        phones.update(f.phones)
        has_amount = has_amount or bool(f.amounts)
        last = message.when
    if current:
        groups.append(current)
    return groups


def extract_candidates(
    messages: list[Message], me: str | None = None, customer_name_hint: str | None = None
) -> list[Candidate]:
    """The conversations that look like orders. `me` is the seller's own name in the chat: the
    customer is then the other person, and only the customer's words count as an order request."""
    facts = [message_facts(m.text) for m in messages]
    mine = (me or "").strip().lower()
    is_me = [bool(mine) and m.sender.strip().lower() == mine for m in messages]
    candidates: list[Candidate] = []

    for group in _conversations(messages, facts):
        used = [i for i in group if facts[i].any]
        # Order words only count when they come from the customer (when we know who that is).
        asked = any(facts[i].strong and not is_me[i] for i in group)
        weak = any(facts[i].weak for i in group)
        amounts = [(v, total, i) for i in group for v, total in facts[i].amounts]
        phones = [(p, i) for i in group for p in facts[i].phones]
        if not (asked or (weak and (amounts or phones)) or (amounts and phones)):
            continue

        first = min(used) if used else group[0]
        # The customer: the other person in the chat, else the one who wrote the first useful message.
        senders = [messages[i].sender for i in group if not is_me[i]]
        by_hint = next((s for s in senders if customer_name_hint and s.lower() == customer_name_hint.lower()), None)
        name = by_hint or (senders[0] if senders else (customer_name_hint or messages[first].sender))

        # Phone: written by the customer first, then anyone, then the number a contact is saved as.
        own = [p for p, i in phones if not is_me[i]]
        known = own or [p for p, _ in phones] or [n for n in map(_phone_like_name, senders) if n]
        phone = known[0] if known else normalise_pk_phone(customer_name_hint or "")
        if _phone_like_name(name):
            name = ""                                    # a number is not a name

        totals = [v for v, total, _ in amounts if total]
        amount = totals[-1] if totals else (max((v for v, _, _ in amounts), default=None))
        others = sorted({v for v, _, _ in amounts if v != amount})

        cities = [c for i in group for c in facts[i].cities]
        any_cod, any_prepaid = any(facts[i].cod for i in group), any(facts[i].prepaid for i in group)
        payment = "cod" if any_cod and not any_prepaid else "prepaid" if any_prepaid and not any_cod else None

        confidence, label = _confidence(amount is not None, phone is not None)
        # A long conversation shows the messages that matter first (those with a fact), in time order.
        shown = sorted((used + [i for i in group if i not in used])[:MAX_SOURCE_MESSAGES])
        candidates.append(Candidate(
            id=len(candidates), customer_name=name, phone=phone, city=cities[0] if cities else None,
            amount=amount, other_amounts=others, payment_type=payment,
            order_date=messages[first].when.date(), order_time=messages[first].when,
            confidence=confidence, confidence_label=label,
            found={"amount": amount is not None, "phone": phone is not None, "keyword": asked or weak, "city": bool(cities)},
            messages=[SourceMessage(messages[i].sender, messages[i].when, messages[i].text[:MAX_SOURCE_TEXT]) for i in shown],
        ))
    return candidates
