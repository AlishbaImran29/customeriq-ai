"""Sending email: through a Google Apps Script web app, Brevo's HTTPS API, or SMTP (for example Gmail).

Passwords and API keys are read from settings and never logged. A failure is reported to the caller as a
friendly error, without the server's own message, so no connection details leak.
"""

import errno
import json
import logging
import smtplib
import socket
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import Settings
from app.core.errors import ApiError

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 15
BREVO_URL = "https://api.brevo.com/v3/smtp/email"
WEBHOOK_TIMEOUT_SECONDS = 25  # a Google Apps Script can take several seconds to wake up
APP_NAME = "CustomerIQ AI"


def _single_line(value: str) -> str:
    """Names go into the body only, but strip line breaks anyway (header injection)."""
    return " ".join(value.split())


def _failure_reason(exc: Exception) -> str:
    """A coarse, safe label for why sending failed (never includes the server's own text)."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (401, 403):
            return "login_refused"  # the API key was not accepted
        if exc.code == 400:
            return "sender_refused"  # usually: the sender address has not been verified at the provider
        if exc.code in (402, 429):
            return "provider_limit"  # sending limit or plan problem at the provider
        return "smtp_error"
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


def _ipv4_connection(host: str, port: int, timeout: float, source_address=None) -> socket.socket:
    """Connect over IPv4 only. Some serverless hosts have no IPv6 route (error 99, "Cannot assign
    requested address"), and trying an IPv6 address first can make the whole connection fail."""
    last: OSError | None = None
    for family, kind, proto, _, address in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
        try:
            return socket.create_connection((address[0], address[1]), timeout, source_address)
        except OSError as exc:
            last = exc
    raise last or socket.gaierror(socket.EAI_NONAME, "no IPv4 address found")


class IPv4SMTP(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        return _ipv4_connection(host, port, timeout, self.source_address)


class IPv4SMTP_SSL(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        sock = _ipv4_connection(host, port, timeout, self.source_address)
        return self.context.wrap_socket(sock, server_hostname=self._host)


class MailProviderError(Exception):
    """The email service answered, but not with success. `reason` is one of the coarse labels."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _send_webhook(settings: Settings, to: str, subject: str, text: str, html: str, headers: dict[str, str] | None = None) -> None:
    """Posts the message to a Google Apps Script web app that sends it from the owner's Gmail.

    Apps Script answers a POST with a redirect to the result page; urllib follows it with a GET,
    which is exactly what Google expects.
    """
    assert settings.mail_webhook_url and settings.mail_webhook_secret
    body = json.dumps(
        {
            "secret": settings.mail_webhook_secret.get_secret_value(),
            "to": to,
            "subject": subject,
            "text": text,
            "html": html,
            "name": APP_NAME,
            "headers": headers or {},          # the script may ignore them
        }
    ).encode()
    request = urllib.request.Request(
        settings.mail_webhook_url, data=body, method="POST", headers={"content-type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=WEBHOOK_TIMEOUT_SECONDS) as response:  # noqa: S310 (https only, checked in settings)
        raw = response.read(65536)
    try:
        answer = json.loads(raw)
    except ValueError as exc:  # for example Google's sign-in page, when the web app is not open to "Anyone"
        raise MailProviderError("bad_response") from exc
    if not isinstance(answer, dict) or not answer.get("ok"):
        raise MailProviderError("login_refused" if isinstance(answer, dict) and answer.get("error") == "forbidden" else "smtp_error")


def sender_address(settings: Settings) -> str | None:
    return settings.mail_from or settings.smtp_from or settings.smtp_user


def _send_smtp(settings: Settings, message: EmailMessage) -> None:
    assert settings.smtp_host and settings.smtp_password
    if settings.smtp_security == "ssl":
        client: smtplib.SMTP = IPv4SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS,
            context=ssl.create_default_context(),
        )
    else:
        client = IPv4SMTP(settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS)
    with client:
        if settings.smtp_security == "starttls":
            client.starttls(context=ssl.create_default_context())
        if settings.smtp_user:
            client.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        client.send_message(message)


def _send_brevo(settings: Settings, sender: str, to: str, subject: str, text: str, html: str, headers: dict[str, str] | None = None) -> None:
    """Brevo's HTTPS API. Unlike SMTP it only needs port 443, so it works on hosts that block mail ports."""
    assert settings.brevo_api_key
    body = json.dumps(
        {
            "sender": {"name": APP_NAME, "email": sender},
            "to": [{"email": to}],
            "subject": subject,
            "textContent": text,
            "htmlContent": html,
            **({"headers": headers} if headers else {}),
        }
    ).encode()
    request = urllib.request.Request(
        BREVO_URL,
        data=body,
        method="POST",
        headers={
            "api-key": settings.brevo_api_key.get_secret_value(),
            "content-type": "application/json",
            "accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=SMTP_TIMEOUT_SECONDS) as response:  # noqa: S310 (fixed https URL)
        response.read()


def send_email(settings: Settings, to: str, subject: str, text: str, html: str, headers: dict[str, str] | None = None) -> None:
    """`headers` are extra email headers (for example List-Unsubscribe). Newlines are stripped from them."""
    headers = {k: _single_line(v) for k, v in (headers or {}).items()}
    sender = sender_address(settings)
    try:
        if settings.mail_webhook_url:
            _send_webhook(settings, to, subject, text, html, headers)
        elif settings.brevo_api_key:
            assert sender
            _send_brevo(settings, sender, to, subject, text, html, headers)
        else:
            assert sender
            message = EmailMessage()
            message["From"] = formataddr((APP_NAME, sender))
            message["To"] = to
            message["Subject"] = subject
            for name, value in headers.items():
                message[name] = value
            message.set_content(text)
            message.add_alternative(html, subtype="html")
            _send_smtp(settings, message)
    except (smtplib.SMTPException, OSError, MailProviderError) as exc:  # HTTP errors are OSErrors too
        reason = exc.reason if isinstance(exc, MailProviderError) else _failure_reason(exc)
        # For an HTTP answer the useful number is the status code (401, 400...), otherwise the OS error number.
        number = exc.code if isinstance(exc, urllib.error.HTTPError) else getattr(exc, "errno", None)
        logger.warning("Could not send email: %s (%s)", type(exc).__name__, reason)
        raise ApiError(
            503, "email_send_failed",
            "We couldn't send the email just now. Please try again in a moment.",
            # `kind` and `errno` are the exception's class name and a number: safe to show the site
            # owner, and enough to tell a blocked network from a TLS, login or sender problem.
            {"reason": reason, "kind": type(exc).__name__, "errno": number},
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
