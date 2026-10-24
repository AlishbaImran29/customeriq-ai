"""Keeping competitor-ad screenshots in Supabase Storage (free tier), in a PRIVATE bucket.

Why private: a screenshot is shown only to a signed-in seller, through a link that expires after an hour.
The bucket and its keys are set up once in the Supabase dashboard (see docs/DEPLOY.md); the service key stays on the
server and is never sent to the browser. Plain `urllib` is used so no extra library is needed.

Screenshots are checked by their first bytes (PNG, JPEG or WebP), not by what the browser says they are.
If storage is not configured, saving an ad still works, only the screenshot is refused with a clear message.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid

from app.core.config import Settings
from app.core.errors import ApiError

MAX_IMAGE_BYTES = 3 * 1024 * 1024               # the host accepts bodies of at most 4.5 MB
SIGNED_URL_SECONDS = 3600
TIMEOUT_SECONDS = 20


def detect_image(content: bytes) -> tuple[str, str] | None:
    """(file extension, mime type) judged from the first bytes, or None when it is not a PNG, JPEG or WebP image."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


def storage_configured(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_service_key and settings.supabase_service_key.get_secret_value().strip())


def _call(settings: Settings, method: str, path: str, body: bytes | None, content_type: str) -> dict:
    base = settings.supabase_url.rstrip("/")  # type: ignore[union-attr]
    key = settings.supabase_service_key.get_secret_value()  # type: ignore[union-attr]
    request = urllib.request.Request(
        f"{base}/storage/v1{path}", data=body, method=method,
        headers={"Authorization": f"Bearer {key}", "apikey": key, "Content-Type": content_type},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:      # noqa: S310 (the address is our own setting)
            raw = response.read()
    except (urllib.error.URLError, TimeoutError):
        raise ApiError(502, "storage_failed", "The file storage did not answer. Please try again.") from None
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}


def upload_screenshot(settings: Settings, project_id: int, content: bytes) -> str:
    """Save an image and return its path inside the bucket."""
    if not storage_configured(settings):
        raise ApiError(503, "storage_not_configured", "Screenshot storage is not set up yet, so the ad was not given a picture. Add SUPABASE_URL and SUPABASE_SERVICE_KEY to the backend settings.")
    if len(content) > MAX_IMAGE_BYTES:
        raise ApiError(413, "image_too_large", "The screenshot is larger than 3 MB. Use a smaller picture.")
    kind = detect_image(content)
    if kind is None:
        raise ApiError(422, "not_an_image", "The screenshot must be a PNG, JPEG or WebP picture.")
    extension, mime = kind
    path = f"project-{project_id}/{uuid.uuid4().hex}.{extension}"
    _call(settings, "POST", f"/object/{urllib.parse.quote(settings.supabase_bucket)}/{path}", content, mime)
    return path


def signed_url(settings: Settings, path: str) -> str | None:
    """A link that works for an hour, or None when storage is not set up or the call fails."""
    if not storage_configured(settings):
        return None
    try:
        answer = _call(settings, "POST", f"/object/sign/{urllib.parse.quote(settings.supabase_bucket)}/{path}",
                       json.dumps({"expiresIn": SIGNED_URL_SECONDS}).encode(), "application/json")
    except ApiError:
        return None
    link = answer.get("signedURL") or answer.get("signedUrl")
    if not link:
        return None
    base = settings.supabase_url.rstrip("/")  # type: ignore[union-attr]
    return link if link.startswith("http") else f"{base}/storage/v1{link}"


def delete_screenshot(settings: Settings, path: str) -> None:
    """Best effort: a failure here must never stop the ad from being deleted."""
    if not storage_configured(settings):
        return
    try:
        _call(settings, "DELETE", f"/object/{urllib.parse.quote(settings.supabase_bucket)}/{path}", None, "application/json")
    except ApiError:
        return


# --- generic helpers for other buckets (customer videos) ---------------------------------------------------------------


def put_object(settings: Settings, bucket: str, path: str, content: bytes, mime: str) -> None:
    """Save bytes in a private bucket. Raises ApiError 503 when storage is not set up, 502 when it does not answer."""
    if not storage_configured(settings):
        raise ApiError(503, "storage_not_configured", "File storage is not set up. Add SUPABASE_URL and SUPABASE_SERVICE_KEY to the backend settings.")
    _call(settings, "POST", f"/object/{urllib.parse.quote(bucket)}/{path}", content, mime)


def signed_url_in(settings: Settings, bucket: str, path: str) -> str | None:
    """A link to a file that works for an hour, or None when storage is not set up or the call fails."""
    if not storage_configured(settings):
        return None
    try:
        answer = _call(settings, "POST", f"/object/sign/{urllib.parse.quote(bucket)}/{path}",
                       json.dumps({"expiresIn": SIGNED_URL_SECONDS}).encode(), "application/json")
    except ApiError:
        return None
    link = answer.get("signedURL") or answer.get("signedUrl")
    if not link:
        return None
    return link if link.startswith("http") else f"{settings.supabase_url.rstrip('/')}/storage/v1{link}"  # type: ignore[union-attr]


def delete_object(settings: Settings, bucket: str, path: str) -> None:
    """Best effort: a failure here must never stop a record from being deleted."""
    if not storage_configured(settings):
        return
    try:
        _call(settings, "DELETE", f"/object/{urllib.parse.quote(bucket)}/{path}", None, "application/json")
    except ApiError:
        return
