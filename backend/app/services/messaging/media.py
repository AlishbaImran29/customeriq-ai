"""Customer videos and photos (Auto Messenger part 3).

THE FLOW
1. A parcel is delivered -> (order_status.py) a WhatsApp message, 2 hours later, asks "did it arrive? send an unboxing video".
2. The customer sends a video or photo. The webhook saves it as `pending` (queue_media) only if the customer is known
   and had a delivery in the last 30 days: a stranger's file is never downloaded.
3. process_pending_media downloads it from the WhatsApp Cloud API, CHECKS it, and stores it in a private bucket.
   Checks: the type must be mp4 / 3gp video or jpeg / png / webp image; the size must be within the limit (16 MB
   video, 5 MB image); and the first bytes must really look like that type (a renamed file is refused).
4. The customer is asked "may we share it on our page? Reply YES or NO" (the stored answer is `share_answer`).
5. Only a YES lets the seller mark the file "usable in ads" (a database constraint enforces it).

Meta's download link works for about 5 minutes and needs the access token, so the file is fetched through the media id.
"""

import json
import logging
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import Customer, CustomerMedia, IncomingMessage, Order, OrderStatusHistory
from app.services import supabase_storage
from app.services.messaging.adapters import GRAPH_URL, whatsapp_configured

logger = logging.getLogger(__name__)

MAX_VIDEO_BYTES = 16 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED = {"video/mp4": ("video", "mp4"), "video/3gpp": ("video", "3gp"), "image/jpeg": ("image", "jpg"), "image/png": ("image", "png"), "image/webp": ("image", "webp")}
RECENT_DELIVERY_DAYS = 30
SHARE_ANSWER_DAYS = 7
MAX_ATTEMPTS = 3
TIMEOUT_SECONDS = 25
CHUNK = 256 * 1024


class MediaRejected(Exception):
    """This file will never be accepted (wrong type, too big, not what it claims to be)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class MediaTemporary(Exception):
    """The download failed for a reason that may pass (network, a busy server). Try again later."""


def base_mime(mime: str | None) -> str:
    return (mime or "").split(";")[0].strip().lower()


def limit_for(mime: str) -> int:
    return MAX_VIDEO_BYTES if ALLOWED[mime][0] == "video" else MAX_IMAGE_BYTES


def looks_right(mime: str, content: bytes) -> bool:
    """Do the first bytes match the claimed type? (mp4 and 3gp files carry an 'ftyp' box right after the 4-byte size.)"""
    if ALLOWED[mime][0] == "video":
        return content[4:8] == b"ftyp"
    found = supabase_storage.detect_image(content)
    return found is not None and found[1] == mime


# --- talking to the WhatsApp Cloud API ------------------------------------------------------------------------------


def _open(settings: Settings, url: str):
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {settings.whatsapp_access_token.get_secret_value()}"})  # type: ignore[union-attr]
    return urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS)          # noqa: S310 (a Meta address)


def media_info(settings: Settings, media_id: str) -> dict:
    """{"url", "mime_type", "file_size"...} for a media id."""
    try:
        with _open(settings, f"{GRAPH_URL}/{settings.whatsapp_api_version}/{media_id}") as response:
            return json.loads(response.read(65536) or b"{}")
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 404):
            raise MediaRejected("media_not_found") from exc
        raise MediaTemporary(f"http_{exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise MediaTemporary("network") from exc


def download(settings: Settings, url: str, limit: int) -> bytes:
    """The file's bytes, stopping as soon as it is bigger than `limit`."""
    data = bytearray()
    try:
        with _open(settings, url) as response:
            while chunk := response.read(CHUNK):
                data.extend(chunk)
                if len(data) > limit:
                    raise MediaRejected("too_large")
    except urllib.error.HTTPError as exc:
        raise MediaTemporary(f"http_{exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MediaTemporary("network") from exc
    return bytes(data)


def fetch_media(settings: Settings, media_id: str) -> tuple[bytes, str]:
    """Download and check one file. Raises MediaRejected or MediaTemporary."""
    info = media_info(settings, media_id)
    mime = base_mime(info.get("mime_type"))
    if mime not in ALLOWED:
        raise MediaRejected("file_type")
    limit = limit_for(mime)
    size = info.get("file_size")
    if isinstance(size, int) and size > limit:
        raise MediaRejected("too_large")
    url = info.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise MediaRejected("no_download_link")
    content = download(settings, url, limit)
    if not content:
        raise MediaRejected("empty_file")
    if not looks_right(mime, content):
        raise MediaRejected("not_really_" + ALLOWED[mime][0])
    return content, mime


# --- queueing and processing ----------------------------------------------------------------------------------------------


def recent_delivered_order(db: Session, customer_id: int, now: datetime) -> Order | None:
    """The customer's most recent order delivered within the last 30 days."""
    since = now - timedelta(days=RECENT_DELIVERY_DAYS)
    row = db.execute(
        select(Order).join(OrderStatusHistory, OrderStatusHistory.order_id == Order.id)
        .where(Order.customer_id == customer_id, OrderStatusHistory.status == "delivered", OrderStatusHistory.at >= since)
        .order_by(OrderStatusHistory.at.desc(), OrderStatusHistory.id.desc()).limit(1)
    ).scalar()
    return row


def queue_media(db: Session, incoming: IncomingMessage, now: datetime | None = None) -> CustomerMedia | None:
    """Note that a customer sent a file. Returns the record, or None when the file is not wanted (an unknown number, or
    nothing was delivered to that customer lately)."""
    now = now or datetime.now(timezone.utc)
    if incoming.customer_id is None or incoming.message_type not in ("image", "video") or not incoming.media_id:
        return None
    existing = db.scalar(select(CustomerMedia).where(CustomerMedia.incoming_message_id == incoming.id))
    if existing is not None:
        return existing
    order = recent_delivered_order(db, incoming.customer_id, now)
    if order is None:
        logger.info("A customer sent a file but had no recent delivery: not downloaded")
        return None
    mime = base_mime(incoming.mime_type)
    media = CustomerMedia(
        customer_id=incoming.customer_id, order_id=order.id, incoming_message_id=incoming.id, media_id=incoming.media_id,
        kind=incoming.message_type, mime_type=mime or None, received_at=incoming.received_at,
    )
    if mime not in ALLOWED:
        media.status, media.error = "rejected", "file_type"                       # kept as a record so the seller can see it was refused
    db.add(media)
    db.flush()
    return media


def process_pending_media(db: Session, settings: Settings, now: datetime | None = None, limit: int = 3) -> dict[str, int]:
    """Download, check and store the files waiting. Commits nothing."""
    now = now or datetime.now(timezone.utc)
    counts = {"stored": 0, "rejected": 0, "failed": 0, "waiting": 0}
    pending = db.scalars(select(CustomerMedia).where(CustomerMedia.status == "pending").order_by(CustomerMedia.id).limit(limit)).all()
    for media in pending:
        if not whatsapp_configured(settings) or not supabase_storage.storage_configured(settings):
            media.error = "not_configured"                                         # kept pending: it is processed once the setup is done
            counts["waiting"] += 1
            continue
        try:
            content, mime = fetch_media(settings, media.media_id)
            kind, extension = ALLOWED[mime]
            path = f"customer-{media.customer_id}/{uuid.uuid4().hex}.{extension}"
            supabase_storage.put_object(settings, settings.supabase_media_bucket, path, content, mime)
        except MediaRejected as rejected:
            media.status, media.error = "rejected", rejected.reason
            counts["rejected"] += 1
            continue
        except (MediaTemporary, ApiError) as problem:
            media.attempts += 1
            media.error = getattr(problem, "code", None) or str(problem)
            if media.attempts >= MAX_ATTEMPTS:
                media.status = "failed"
                counts["failed"] += 1
            else:
                counts["waiting"] += 1
            continue
        media.status, media.error, media.storage_path, media.size_bytes, media.mime_type, media.kind = "stored", None, path, len(content), mime, kind
        counts["stored"] += 1
        ask_to_share(db, settings, media, now)
    return counts


def ask_to_share(db: Session, settings: Settings, media: CustomerMedia, now: datetime) -> None:
    """Send "may we share your video? Reply YES or NO" (the customer just wrote to us, so WhatsApp allows free text)."""
    from app.services import order_status
    from app.services.messaging import service
    from app.services.messaging.settings_store import get_row

    customer, order = db.get(Customer, media.customer_id), (db.get(Order, media.order_id) if media.order_id else None)
    if customer is None:
        return
    row = get_row(db)
    template = order_status.pick_template(db, "media_share_question", "whatsapp", order_status.customer_language(customer, row.default_language), row.default_language)
    if template is None:
        logger.info("No media_share_question template: the customer was not asked")
        return
    extra = order_status.order_variables(db, order, customer, "delivered", template.language, None, None) if order else {}
    message = service.send_message(
        db, settings, customer, "whatsapp", template, service.customer_variables(customer, row, template.language, extra),
        event_key=f"media:{media.id}:share_question", event="media_share_question", order_id=media.order_id, now=now,
    )
    media.question_sent = message.status in ("sent", "queued", "delivered", "read")


def apply_share_answer(db: Session, customer_id: int, answer: str, now: datetime | None = None) -> CustomerMedia | None:
    """The customer replied YES or NO: record it on their latest file that was waiting for an answer."""
    now = now or datetime.now(timezone.utc)
    media = db.scalar(
        select(CustomerMedia).where(
            CustomerMedia.customer_id == customer_id, CustomerMedia.status == "stored", CustomerMedia.question_sent.is_(True),
            CustomerMedia.share_answer == "pending", CustomerMedia.received_at >= now - timedelta(days=SHARE_ANSWER_DAYS),
        ).order_by(CustomerMedia.id.desc()).limit(1)
    )
    if media is None or answer not in ("yes", "no"):
        return None
    media.share_answer = answer
    if answer == "no":
        media.usable_in_ads, media.usable_marked_at = False, None
    return media


def set_usable(media: CustomerMedia, usable: bool, now: datetime | None = None) -> None:
    """The seller marks a file usable in ads. Allowed only after the customer said YES."""
    if usable and (media.status != "stored" or media.share_answer != "yes"):
        raise ApiError(409, "no_permission", "This file can be used in ads only after the customer has answered YES to sharing it.")
    media.usable_in_ads = usable
    media.usable_marked_at = (now or datetime.now(timezone.utc)) if usable else None
