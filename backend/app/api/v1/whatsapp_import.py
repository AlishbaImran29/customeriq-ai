"""Import orders from a WhatsApp "Export chat" file, with the seller's review in between.

The chat file is read in memory and thrown away. Nothing of it is written to disk, saved in the
database or logged. The candidate orders (with their original messages, for the review screen) go
back to the browser; only the orders the seller accepts come back to be saved, and those carry no
chat text. See services/whatsapp_chat.py, chat_orders.py and whatsapp_orders.py.
"""

from fastapi import APIRouter, Depends, Form, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db
from app.schemas.whatsapp_import import (
    CandidateOut,
    ChatMessageOut,
    ChatParseOut,
    ChatSenderOut,
    WhatsAppDeleteOut,
    WhatsAppSaveIn,
    WhatsAppSaveOut,
    WhatsAppSummaryOut,
)
from app.services import whatsapp_orders
from app.services.chat_orders import Candidate, extract_candidates
from app.services.whatsapp_chat import parse_chat

# Vercel accepts request bodies of at most 4.5 MB, so a chat above 4 MB could never arrive anyway.
MAX_CHAT_BYTES = 4 * 1024 * 1024
MAX_CANDIDATES = 500
_CHUNK = 1024 * 1024

router = APIRouter(prefix="/whatsapp-import", tags=["whatsapp-import"])


async def _read_limited(file: UploadFile) -> bytes:
    data = bytearray()
    while chunk := await file.read(_CHUNK):
        data.extend(chunk)
        if len(data) > MAX_CHAT_BYTES:
            raise ApiError(
                413, "file_too_large",
                "This chat is too big (4 MB at most). Export fewer months of the chat and try again.",
            )
    return bytes(data)


def _candidate_out(c: Candidate) -> CandidateOut:
    return CandidateOut(
        id=c.id, customer_name=c.customer_name, phone=c.phone, city=c.city,
        amount=float(c.amount) if c.amount is not None else None,
        other_amounts=[float(a) for a in c.other_amounts], payment_type=c.payment_type,
        order_date=c.order_date, order_time=c.order_time, confidence=c.confidence,
        confidence_label=c.confidence_label, found=c.found,
        messages=[ChatMessageOut(sender=m.sender, time=m.when, text=m.text) for m in c.messages],
    )


def _analyse(content: bytes, filename: str, date_order: str | None, me: str | None) -> ChatParseOut:
    text = content.decode("utf-8-sig", errors="replace")
    chat = parse_chat(text, filename, date_order if date_order in ("dmy", "mdy") else None)  # type: ignore[arg-type]
    names = {name for name, _ in chat.senders}
    chosen = me if me in names else None
    found = extract_candidates(chat.messages, me=chosen, customer_name_hint=chat.customer_name_hint)
    return ChatParseOut(
        date_order=chat.date_order, date_order_ambiguous=chat.date_order_ambiguous,
        senders=[ChatSenderOut(name=n, messages=c) for n, c in chat.senders], me=chosen,
        customer_name_hint=chat.customer_name_hint, message_count=len(chat.messages),
        system_lines=chat.system_lines, media_messages=chat.media_messages,
        unreadable_lines=chat.unreadable_lines,
        candidates=[_candidate_out(c) for c in found[:MAX_CANDIDATES]], truncated=len(found) > MAX_CANDIDATES,
    )


@router.post("/parse", response_model=ChatParseOut, summary="Read a WhatsApp chat export and suggest orders")
async def parse_whatsapp_chat(
    file: UploadFile, date_order: str | None = Form(None, alias="dateOrder"), me: str | None = Form(None)
) -> ChatParseOut:
    """Nothing is saved. The file is read in memory and discarded when this request ends."""
    filename = (file.filename or "chat.txt")[:255]
    if filename.lower().endswith(".zip"):
        raise ApiError(415, "unsupported_file_type", "Unzip the export and upload the .txt file inside it.")
    if not filename.lower().endswith(".txt"):
        raise ApiError(415, "unsupported_file_type", "Upload the .txt file made by WhatsApp's Export chat.")
    content = await _read_limited(file)
    if not content.strip():
        raise ApiError(400, "empty_file", "The file is empty.")
    return await run_in_threadpool(_analyse, content, filename, date_order, me)


@router.post("/save", response_model=WhatsAppSaveOut, status_code=status.HTTP_201_CREATED, summary="Save the accepted orders")
def save_accepted(body: WhatsAppSaveIn, db: Session = Depends(get_db)) -> WhatsAppSaveOut:
    """Save the orders the seller accepted: all, or none if any has a problem (reported by row)."""
    result = whatsapp_orders.save_accepted_orders(db, [o.model_dump(by_alias=True) for o in body.orders])
    return WhatsAppSaveOut(saved=result.saved, already_imported=result.already_imported, new_customers=result.new_customers)


@router.get("/summary", response_model=WhatsAppSummaryOut, summary="How much WhatsApp data is saved")
def summary(db: Session = Depends(get_db)) -> WhatsAppSummaryOut:
    orders, customers = whatsapp_orders.summary(db)
    return WhatsAppSummaryOut(orders=orders, customers=customers)


@router.delete("", response_model=WhatsAppDeleteOut, summary="Delete all imported WhatsApp data")
def delete_all(db: Session = Depends(get_db)) -> WhatsAppDeleteOut:
    """Deletes every order imported from a WhatsApp chat, and the customers left with no orders."""
    orders, customers = whatsapp_orders.delete_all(db)
    return WhatsAppDeleteOut(orders_deleted=orders, customers_deleted=customers)
