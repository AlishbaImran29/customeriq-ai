"""Password hashing, session tokens, and the password policy.

Uses only the standard library: scrypt for passwords (slow on purpose, so guessing
is expensive) and SHA-256 for session-token lookups.
"""

import base64
import hashlib
import hmac
import re
import secrets

# scrypt cost (OWASP-recommended combination). Tests lower N to run fast.
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 3
_MAX_MEMORY = 256 * 1024 * 1024

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "1234567890", "12345678910", "qwertyuiop",
    "iloveyou123", "admin12345", "welcome123", "letmein123", "customeriq", "customeriq123",
}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_MAX_MEMORY, dklen=32
    )


def hash_password(password: str) -> str:
    """Return "scrypt$N$r$p$salt$hash". The cost is stored so it can be raised later."""
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check. Any malformed stored hash simply fails."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalise_email(email: str) -> str:
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    return len(email) <= 320 and bool(_EMAIL.match(email))


def password_problem(password: str, email: str = "") -> str | None:
    """A friendly sentence describing what is wrong with the password, or None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Use at least {MIN_PASSWORD_LENGTH} characters. A few random words in a row work well."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Use at most {MAX_PASSWORD_LENGTH} characters."
    lowered = password.lower()
    if lowered in _COMMON_PASSWORDS or password.isdigit() or len(set(lowered)) < 4:
        return "That password is too easy to guess. Try a few unrelated words together."
    local = normalise_email(email).split("@")[0] if email else ""
    if local and len(local) >= 4 and local in lowered:
        return "Don't use your email name in your password."
    return None
