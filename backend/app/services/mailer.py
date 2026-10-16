"""Sending email through SMTP (for example Gmail with an App Password).

The password is read from settings and never logged. A failure is reported to the caller as a
friendly error, without the server's own message, so no connection details leak.
"""

import errno
import logging
import smtplib
import socket
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


def _failure_reason(exc: Exception) -> str:
    """A coarse, safe label for why sending failed (never includes the server's own text)."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "login_refused"
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "sender_refused"
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "address_refused"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, smtplib.SMTPServerDisconnected | smtplib.SMTPConnectError):
        return "disconnected"
    if isinstance(exc, ssl.SSLError):
        return "tls_failed"  # the encrypted handshake failed (often SMTP_PORT and SMTP_SECURITY do not match)
    if isinstance(exc, socket.gaierror):
        return "host_not_found"  # the host name does not exist (usually a typo in SMTP_HOST)
    if isinstance(exc, ConnectionRefusedError):
        return "port_closed"  # the host answered but nothing listens on that port
    if isinstance(exc, OSError) and exc.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH):
        return "network_blocked"  # this server has no route to the email service
    if isinstance(exc, OSError):
        return "unreachable"
    return "smtp_error"


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
        reason = _failure_reason(exc)
        logger.warning("Could not send email: %s (%s)", type(exc).__name__, reason)
        raise ApiError(
            503, "email_send_failed",
            "We couldn't send the email just now. Please try again in a moment.",
            # `kind` and `errno` are the exception's class name and OS error number: safe to show
            # the site owner, and enough to tell a blocked network from a TLS or login problem.
            {"reason": reason, "kind": type(exc).__name__, "errno": getattr(exc, "errno", None)},
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
