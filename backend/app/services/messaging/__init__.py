"""Auto Messenger: automatic, consent-based WhatsApp and email messages.

The pieces, in the order a message travels:
    render.py    fills {{variables}} into a template (and refuses to invent a missing one)
    consent.py   who agreed to be messaged, and the history of every change
    policy.py    quiet hours and the weekly marketing cap (pure functions, easy to test)
    service.py   send(): consent -> template approval -> render -> cap -> quiet hours -> adapter -> status
    adapters.py  WhatsApp Cloud API, email (the existing mailer) and a dry-run that sends nothing
    webhook.py   what Meta tells us back: delivered, read, replies, and STOP
"""
