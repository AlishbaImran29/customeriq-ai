"""Sending email through SMTP (for example Gmail with an App Password).

The password is read from settings and never logged. A failure is reported to the caller as a
friendly error, without the server's own message, so no connection details leak.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import Settings
from app.core.errors import ApiError

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 15
APP_NAME = "CustomerIQ AI"


def _single_line(value: str) -> str:
    """Names go into the body only, but strip line breaks anyway (header injection)."""
    return " ".join(value.split())


def send_email(settings: Settings, to: str, subject: str, text: str, html: str) -> None:
    sender = settings.smtp_from or settings.smtp_user
    assert settings.smtp_host and sender and settings.smtp_password
    message = EmailMessage()
    message["From"] = formataddr((APP_NAME, sender))
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    try:
        if settings.smtp_security == "ssl":
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS,
                context=ssl.create_default_context(),
            )
        else:
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS)
        with client:
            if settings.smtp_security == "starttls":
                client.starttls(context=ssl.create_default_context())
            if settings.smtp_user:
                client.login(settings.smtp_user, settings.smtp_password.get_secret_value())
            client.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("Could not send email: %s", type(exc).__name__)
        raise ApiError(
            503, "email_send_failed",
            "We couldn't send the email just now. Please try again in a moment.",
        ) from exc


def send_verification_code(settings: Settings, to: str, name: str, code: str, minutes: int) -> None:
    who = _single_line(name) or "there"
    text = (
        f"Hi {who},\n\n"
        f"Your {APP_NAME} verification code is: {code}\n\n"
        f"It expires in {minutes} minutes. If you did not try to create an account, you can ignore this email.\n"
    )
    html = (
        f"<div style=\"font-family:Arial,sans-serif;max-width:480px;margin:auto;color:#0f172a\">"
        f"<h2 style=\"margin:0 0 8px\">{APP_NAME}</h2>"
        f"<p>Hi {who.replace('<', '&lt;').replace('>', '&gt;')},</p>"
        f"<p>Your verification code is:</p>"
        f"<p style=\"font-size:32px;letter-spacing:8px;font-weight:bold;margin:16px 0\">{code}</p>"
        f"<p style=\"color:#475569\">It expires in {minutes} minutes. If you did not try to create an account, "
        f"you can ignore this email.</p></div>"
    )
    send_email(settings, to, f"{code} is your {APP_NAME} verification code", text, html)
