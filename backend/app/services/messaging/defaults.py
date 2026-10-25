"""The ready-made templates ("Add the default templates" in the Templates page).

They are a starting point in Urdu and English. NONE of them is approved when it is added: the seller reads each
one, changes what they like, and approves it (project rule 3). For WhatsApp the seller also creates the same text
in Meta's WhatsApp Manager and marks it approved there before real sending works (see `meta_style` in render.py).

Order updates are UTILITY messages (a customer who ordered expects them). The unboxing, share and review messages
are written as utility follow-ups on an order; if Meta classifies one differently, change its category.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MessageTemplate

ORDER_EVENTS = ("confirmed", "dispatched", "in_transit", "out_for_delivery", "delivered", "returned")

# --- orders: (english, urdu) per status; the email text repeats the WhatsApp text and adds the shop name ---------

_ORDER_EN = {
    "confirmed": ("Your order {{order_number}} is confirmed",
                  "Hello {{first_name}}, thank you for your order {{order_number}} from {{store_name}}.\nItems: {{items}}\nTotal: {{amount}}\n{{cod_note}}"),
    "dispatched": ("Your order {{order_number}} has been dispatched",
                   "Hello {{first_name}}, your order {{order_number}} has been dispatched.\n{{tracking_line}}\n{{cod_note}}"),
    "in_transit": ("Your order {{order_number}} is on its way",
                   "Hello {{first_name}}, your order {{order_number}} is on its way to you.\n{{tracking_line}}"),
    "out_for_delivery": ("Your order {{order_number}} is out for delivery today",
                         "Hello {{first_name}}, your order {{order_number}} is out for delivery today.\n{{cod_note}}\n{{tracking_line}}"),
    "delivered": ("Your order {{order_number}} was delivered",
                  "Hello {{first_name}}, your order {{order_number}} has been delivered. Thank you for shopping with {{store_name}}!"),
    "returned": ("Your order {{order_number}} is being returned",
                 "Hello {{first_name}}, your order {{order_number}} is being returned to {{store_name}}. If you have any question, just reply to this message."),
}
_ORDER_UR = {
    "confirmed": ("آپ کا آرڈر {{order_number}} کنفرم ہو گیا",
                  "السلام علیکم {{first_name}}، {{store_name}} سے آپ کے آرڈر {{order_number}} کا شکریہ۔\nاشیاء: {{items}}\nکل رقم: {{amount}}\n{{cod_note}}"),
    "dispatched": ("آپ کا آرڈر {{order_number}} روانہ کر دیا گیا",
                   "السلام علیکم {{first_name}}، آپ کا آرڈر {{order_number}} روانہ کر دیا گیا ہے۔\n{{tracking_line}}\n{{cod_note}}"),
    "in_transit": ("آپ کا آرڈر {{order_number}} آپ کی طرف آ رہا ہے",
                   "السلام علیکم {{first_name}}، آپ کا آرڈر {{order_number}} آپ کی طرف آ رہا ہے۔\n{{tracking_line}}"),
    "out_for_delivery": ("آپ کا آرڈر {{order_number}} آج ڈیلیوری کے لیے نکل چکا ہے",
                         "السلام علیکم {{first_name}}، آپ کا آرڈر {{order_number}} آج ڈیلیوری کے لیے نکل چکا ہے۔\n{{cod_note}}\n{{tracking_line}}"),
    "delivered": ("آپ کا آرڈر {{order_number}} ڈیلیور ہو گیا",
                  "السلام علیکم {{first_name}}، آپ کا آرڈر {{order_number}} ڈیلیور ہو گیا ہے۔ {{store_name}} سے خریداری کا شکریہ!"),
    "returned": ("آپ کا آرڈر {{order_number}} واپس کیا جا رہا ہے",
                 "السلام علیکم {{first_name}}، آپ کا آرڈر {{order_number}} {{store_name}} کو واپس کیا جا رہا ہے۔ کوئی سوال ہو تو اسی پیغام کا جواب دیں۔"),
}

# --- delivered follow-ups (part 3) ------------------------------------------------------------------------------------

_FOLLOWUPS = {
    "delivered_unboxing": {
        "en": ("Did your order {{order_number}} arrive safely?",
               "Hello {{first_name}}, did your order {{order_number}} reach you safely? If you like, send us a short unboxing video or photo in this chat. We would love to see it!"),
        "ur": ("کیا آپ کا آرڈر {{order_number}} خیریت سے پہنچ گیا؟",
               "السلام علیکم {{first_name}}، کیا آپ کا آرڈر {{order_number}} خیریت سے پہنچ گیا؟ اگر چاہیں تو اس چیٹ میں ایک مختصر ان باکسنگ ویڈیو یا تصویر بھیجیں۔ ہمیں دیکھ کر خوشی ہوگی!"),
    },
    "media_share_question": {
        "en": ("May we share your video?",
               "Thank you for sending this, {{first_name}}! May we share it on our page? Reply YES or NO."),
        "ur": ("کیا ہم آپ کی ویڈیو شیئر کر سکتے ہیں؟",
               "شکریہ {{first_name}}! کیا ہم اسے اپنے پیج پر شیئر کر سکتے ہیں؟ جواب میں YES یا NO لکھیں۔"),
    },
    "cod_confirmation": {
        "en": ("Please confirm your order {{order_number}}",
               "Hello {{first_name}}, you placed a cash-on-delivery order {{order_number}} ({{items}}) for {{amount}}. Reply YES to confirm it, or NO to cancel it."),
        "ur": ("براہ کرم اپنا آرڈر {{order_number}} کنفرم کریں",
               "السلام علیکم {{first_name}}، آپ نے کیش آن ڈیلیوری آرڈر {{order_number}} ({{items}}) بقیمت {{amount}} دیا ہے۔ کنفرم کرنے کے لیے YES اور منسوخ کرنے کے لیے NO لکھیں۔"),
    },
    "review_request": {
        "en": ("How is your order {{order_number}}?",
               "Hello {{first_name}}, we hope you are enjoying your order {{order_number}}. If you have a minute, please share your honest review: {{review_link}}"),
        "ur": ("آپ کا آرڈر {{order_number}} کیسا رہا؟",
               "السلام علیکم {{first_name}}، امید ہے آپ کو آرڈر {{order_number}} پسند آیا ہوگا۔ اگر وقت ہو تو اپنی سچی رائے یہاں لکھیں: {{review_link}}"),
    },
}


# --- abandoned cart reminders (marketing, because they invite a purchase) -------------------------------------------------

_CARTS = {
    "cart_reminder_1": {
        "en": ("You left something behind", "Hello {{first_name}}, you left {{items}} in your cart at {{store_name}}. You can finish your order here: {{checkout_url}}"),
        "ur": ("آپ کچھ چھوڑ گئے", "السلام علیکم {{first_name}}، آپ نے {{store_name}} پر {{items}} اپنی ٹوکری میں چھوڑا ہے۔ اپنا آرڈر یہاں مکمل کریں: {{checkout_url}}"),
    },
    "cart_reminder_2": {
        "en": ("Still thinking it over?", "Hello {{first_name}}, your cart at {{store_name}} is still waiting: {{items}}. Finish your order any time: {{checkout_url}}"),
        "ur": ("کیا ابھی سوچ رہے ہیں؟", "السلام علیکم {{first_name}}، {{store_name}} پر آپ کی ٹوکری ابھی موجود ہے: {{items}}۔ جب چاہیں آرڈر مکمل کریں: {{checkout_url}}"),
    },
}


_RETURNS = {
    "return_approved": {
        "en": ("Your return for order {{order_number}} is approved", "Hello {{first_name}}, we approved your return request for order {{order_number}}. We will tell you the next step soon."),
        "ur": ("آرڈر {{order_number}} کی واپسی منظور ہو گئی", "السلام علیکم {{first_name}}، آپ کے آرڈر {{order_number}} کی واپسی کی درخواست منظور ہو گئی ہے۔ اگلا قدم جلد بتائیں گے۔"),
    },
    "return_rejected": {
        "en": ("About your return request for order {{order_number}}", "Hello {{first_name}}, we could not approve the return request for order {{order_number}}. Please reply to this message if you would like to talk about it."),
        "ur": ("آرڈر {{order_number}} کی واپسی کے بارے میں", "السلام علیکم {{first_name}}، ہم آرڈر {{order_number}} کی واپسی منظور نہیں کر سکے۔ بات کرنے کے لیے اسی پیغام کا جواب دیں۔"),
    },
    "refund_recorded": {
        "en": ("Your refund for order {{order_number}}", "Hello {{first_name}}, we have sent your refund for order {{order_number}}. If you do not see it soon, please reply and tell us."),
        "ur": ("آرڈر {{order_number}} کا ریفنڈ", "السلام علیکم {{first_name}}، ہم نے آرڈر {{order_number}} کا ریفنڈ بھیج دیا ہے۔ اگر جلد نظر نہ آئے تو جواب میں بتائیں۔"),
    },
}


SIGNATURE = "\n\n{{store_name}}"                 # the shop's name under every email


def _rows() -> list[dict]:
    rows: list[dict] = []

    def add(event: str, channel: str, language: str, subject: str, body: str, category: str = "utility") -> None:
        name = f"{event}_{language}" if channel == "whatsapp" else f"{event}_{language}_email"
        rows.append({
            "name": name, "channel": channel, "category": category, "language": language, "event": event,
            "subject": subject if channel == "email" else None, "body": body + (SIGNATURE if channel == "email" else ""),
            "meta_template_name": f"{event}_{language}" if channel == "whatsapp" else None,
        })

    for status in ORDER_EVENTS:
        for language, table in (("en", _ORDER_EN), ("ur", _ORDER_UR)):
            subject, body = table[status]
            for channel in ("whatsapp", "email"):
                add(f"order_{status}", channel, language, subject, body)
    for event, languages in _FOLLOWUPS.items():
        for language, (subject, body) in languages.items():
            for channel in ("whatsapp", "email"):
                if event in ("media_share_question", "cod_confirmation") and channel == "email":
                    continue                       # the YES/NO answer comes back on WhatsApp
                add(event, channel, language, subject, body)
    for event, languages in _RETURNS.items():
        for language, (subject, body) in languages.items():
            for channel in ("whatsapp", "email"):
                add(event, channel, language, subject, body)
    for event, languages in _CARTS.items():
        for language, (subject, body) in languages.items():
            for channel in ("whatsapp", "email"):
                add(event, channel, language, subject, body, category="marketing")
    return rows


DEFAULT_GROUPS = {
    "orders": lambda r: r["event"].startswith("order_"),
    "followups": lambda r: r["event"] in _FOLLOWUPS,
    "carts": lambda r: r["event"] in _CARTS,
    "returns": lambda r: r["event"] in _RETURNS,
}


def default_templates(groups: list[str] | None = None) -> list[dict]:
    chosen = list(DEFAULT_GROUPS) if groups is None else groups          # None = all groups; an empty list = none
    return [r for r in _rows() if any(DEFAULT_GROUPS[g](r) for g in chosen if g in DEFAULT_GROUPS)]


def seed_defaults(db: Session, groups: list[str] | None = None, extra: list[dict] | None = None) -> int:
    """Add the default templates that do not exist yet (by name, channel and language). Never overwrites a template the
    seller has edited. Returns how many were added. Does not commit."""
    added = 0
    for row in [*default_templates(groups), *(extra or [])]:
        exists = db.scalar(select(MessageTemplate.id).where(MessageTemplate.name == row["name"], MessageTemplate.channel == row["channel"], MessageTemplate.language == row["language"]))
        if exists is None:
            db.add(MessageTemplate(is_default=True, approved_by_seller=False, **row))
            added += 1
    db.flush()
    return added
