"""The default journeys and their message templates (the seller can edit and approve all of them).

None of the wording promises a discount or invents a fact: the messages only thank, ask, and invite a reply. If the
seller wants to mention an offer, they edit the template and approve it. Every WhatsApp text ends with the STOP
instruction (a marketing template cannot be approved without it); emails get an unsubscribe link automatically.
"""

JOURNEYS: list[dict] = [
    {
        "key": "champions", "name": "Champions: thank you and early access", "trigger_segment": "Champions", "anchor": "enrollment",
        "description": "Thank your best customers and offer early access. At most 2 messages in any 30 days.",
        "steps": [{"day": 0, "event": "journey_champions"}], "loop_every_days": 15, "max_sends": None, "max_per_30_days": 2, "grace_days": 3,
    },
    {
        "key": "loyal", "name": "Loyal Customers: what is new", "trigger_segment": "Loyal Customers", "anchor": "enrollment",
        "description": "Tell regular customers about new things, every 14 days.",
        "steps": [{"day": 0, "event": "journey_loyal"}], "loop_every_days": 14, "max_sends": None, "max_per_30_days": None, "grace_days": 3,
    },
    {
        "key": "potential", "name": "New and growing customers: day 7 and day 21", "trigger_segment": "Potential Loyalists", "anchor": "first_order",
        "description": "Two friendly messages after a customer's first order: on day 7 and on day 21.",
        "steps": [{"day": 7, "event": "journey_potential_1"}, {"day": 21, "event": "journey_potential_2"}],
        "loop_every_days": None, "max_sends": None, "max_per_30_days": None, "grace_days": 3,
    },
    {
        "key": "at_risk", "name": "At-Risk: win-back", "trigger_segment": "At-Risk Customers", "anchor": "enrollment",
        "description": "A win-back message when a customer becomes At-Risk, then 7 and 14 days later. Then it stops.",
        "steps": [{"day": 0, "event": "journey_at_risk_1"}, {"day": 7, "event": "journey_at_risk_2"}, {"day": 14, "event": "journey_at_risk_3"}],
        "loop_every_days": None, "max_sends": None, "max_per_30_days": None, "grace_days": 3,
    },
    {
        "key": "lost", "name": "Lost Customers: a monthly reminder, twice", "trigger_segment": "Lost Customers", "anchor": "enrollment",
        "description": "One gentle message a month, at most 2 times in total. Then it stops.",
        "steps": [{"day": 0, "event": "journey_lost"}], "loop_every_days": 30, "max_sends": 2, "max_per_30_days": None, "grace_days": 3,
    },
]

_STOP = {"en": "\n\nReply STOP to stop messages.", "ur": "\n\nپیغامات بند کرنے کے لیے STOP لکھیں۔"}

# event -> language -> (email subject, body). {{last_purchase_line}} is left out when we do not know the last purchase.
_TEXT: dict[str, dict[str, tuple[str, str]]] = {
    "journey_champions": {
        "en": ("Thank you from {{store_name}}", "Hello {{first_name}}, you are one of our best customers at {{store_name}}, and we are grateful. {{last_purchase_line}}\nReply to this message and we will tell you about new arrivals before anyone else."),
        "ur": ("{{store_name}} کی طرف سے شکریہ", "السلام علیکم {{first_name}}، آپ {{store_name}} کے بہترین کسٹمرز میں سے ہیں، ہم آپ کے شکر گزار ہیں۔ {{last_purchase_line}}\nاس پیغام کا جواب دیں، ہم نئی چیزوں کے بارے میں سب سے پہلے آپ کو بتائیں گے۔"),
    },
    "journey_loyal": {
        "en": ("What is new at {{store_name}}", "Hello {{first_name}}, thank you for being a regular at {{store_name}}. {{last_purchase_line}}\nWe have new things in store: reply to this message and we will show you."),
        "ur": ("{{store_name}} میں کیا نیا ہے", "السلام علیکم {{first_name}}، {{store_name}} کا مستقل کسٹمر ہونے کا شکریہ۔ {{last_purchase_line}}\nہمارے پاس نئی چیزیں آئی ہیں: اس پیغام کا جواب دیں، ہم آپ کو دکھائیں گے۔"),
    },
    "journey_potential_1": {
        "en": ("How is your order from {{store_name}}?", "Hello {{first_name}}, we hope you are enjoying your order from {{store_name}}. If you would like to see more like it, just reply to this message."),
        "ur": ("{{store_name}} سے آپ کا آرڈر کیسا رہا؟", "السلام علیکم {{first_name}}، امید ہے آپ کو {{store_name}} سے اپنا آرڈر پسند آیا ہوگا۔ اس جیسی مزید چیزیں دیکھنی ہوں تو اس پیغام کا جواب دیں۔"),
    },
    "journey_potential_2": {
        "en": ("Thinking of you from {{store_name}}", "Hello {{first_name}}, it has been a few weeks since your first order at {{store_name}}. {{last_purchase_line}}\nReply if you would like a recommendation."),
        "ur": ("{{store_name}} کی طرف سے", "السلام علیکم {{first_name}}، {{store_name}} سے آپ کے پہلے آرڈر کو کچھ ہفتے ہو گئے ہیں۔ {{last_purchase_line}}\nکوئی مشورہ چاہیے تو جواب دیں۔"),
    },
    "journey_at_risk_1": {
        "en": ("We have missed you at {{store_name}}", "Hello {{first_name}}, we have missed you at {{store_name}}. {{last_purchase_line}}\nIs there anything we can help you with? Just reply to this message."),
        "ur": ("{{store_name}} میں ہم نے آپ کو یاد کیا", "السلام علیکم {{first_name}}، ہم نے {{store_name}} میں آپ کو یاد کیا۔ {{last_purchase_line}}\nکیا ہم آپ کی کوئی مدد کر سکتے ہیں؟ بس اس پیغام کا جواب دیں۔"),
    },
    "journey_at_risk_2": {
        "en": ("Checking in from {{store_name}}", "Hello {{first_name}}, just checking in from {{store_name}}. If something was not right with your last order, please tell us and we will make it better."),
        "ur": ("{{store_name}} کی طرف سے خیریت", "السلام علیکم {{first_name}}، {{store_name}} کی طرف سے خیریت دریافت کر رہے ہیں۔ اگر آپ کے پچھلے آرڈر میں کوئی مسئلہ تھا تو بتائیں، ہم اسے بہتر کریں گے۔"),
    },
    "journey_at_risk_3": {
        "en": ("One last note from {{store_name}}", "Hello {{first_name}}, this is our last note for now. We would love to see you again at {{store_name}}. Reply any time."),
        "ur": ("{{store_name}} کی طرف سے آخری پیغام", "السلام علیکم {{first_name}}، یہ ہمارا فی الحال آخری پیغام ہے۔ ہم آپ کو {{store_name}} میں دوبارہ دیکھنا چاہیں گے۔ جب چاہیں جواب دیں۔"),
    },
    "journey_lost": {
        "en": ("It has been a while", "Hello {{first_name}}, it has been a long time since we last saw you at {{store_name}}. We would be happy to hear from you again."),
        "ur": ("کافی وقت ہو گیا", "السلام علیکم {{first_name}}، آپ کو {{store_name}} میں دیکھے کافی وقت ہو گیا ہے۔ ہمیں آپ کا جواب سن کر خوشی ہوگی۔"),
    },
}


def journey_templates() -> list[dict]:
    """Template rows (WhatsApp and email, English and Urdu) for every journey step."""
    rows = []
    for event, languages in _TEXT.items():
        for language, (subject, body) in languages.items():
            rows.append({"name": f"{event}_{language}", "channel": "whatsapp", "category": "marketing", "language": language, "event": event,
                         "subject": None, "body": body + _STOP[language], "meta_template_name": f"{event}_{language}"})
            rows.append({"name": f"{event}_{language}_email", "channel": "email", "category": "marketing", "language": language, "event": event,
                         "subject": subject, "body": body + "\n\n{{store_name}}", "meta_template_name": None})
    return rows
