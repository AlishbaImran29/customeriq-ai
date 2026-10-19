"""WhatsApp chat parser: Android and iPhone layouts, dates, system lines, and privacy.

Every chat used here is made up (see tests/fixtures/whatsapp/README.md).
"""

import logging
from datetime import datetime
from pathlib import Path

import pytest

from app.services.chat_orders import extract_candidates
from app.services.whatsapp_chat import detect_date_order, name_from_filename, parse_chat

FIXTURES = Path(__file__).parent / "fixtures" / "whatsapp"


def load(name: str, filename: str | None = None, **kw):
    return parse_chat((FIXTURES / name).read_text(encoding="utf-8"), filename, **kw)


def test_every_fixture_is_marked_as_made_up_test_data():
    files = sorted(FIXTURES.glob("*.txt"))
    assert len(files) >= 6
    for f in files:
        assert f.name.startswith("TESTDATA_")
        assert f.read_text(encoding="utf-8").splitlines()[0].startswith("TEST DATA ONLY")


# --- Android, 12 hour clock ---------------------------------------------------------------------

def test_android_12_hour_chat():
    chat = load("TESTDATA_android_12h.txt")
    assert chat.date_order == "dmy" and chat.date_order_ambiguous is False   # 19/10 can only be day-first
    first = chat.messages[0]
    assert (first.sender, first.when) == ("Ayesha", datetime(2026, 10, 18, 21, 15))   # 9:15 pm is 21:15
    assert first.text == "Assalam o alaikum, mujhe 2 lawn suits chahiye"
    assert any(m.when == datetime(2026, 10, 19, 11, 30) for m in chat.messages)         # 11:30 am stays 11:30
    assert [name for name, _ in chat.senders][:2] == ["Ayesha", "Sana Boutique"] or chat.senders[0][1] >= chat.senders[1][1]


def test_system_lines_media_and_deleted_messages_are_left_out():
    chat = load("TESTDATA_android_12h.txt")
    texts = [m.text for m in chat.messages]
    assert not any("end-to-end" in t or "Media omitted" in t or "deleted" in t for t in texts)
    assert chat.system_lines == 2 and chat.media_messages == 1          # encryption notice + "You deleted"; one photo


def test_a_message_over_several_lines_is_one_message():
    chat = load("TESTDATA_android_12h.txt")
    confirm = next(m for m in chat.messages if m.text.startswith("Theek hai confirm"))
    assert "House 12, Street 4, Gulberg, Lahore" in confirm.text and "0300-1234567" in confirm.text
    assert confirm.text.count("\n") == 2


# --- Android 24 hour, iPhone ----------------------------------------------------------------------

def test_android_24_hour_chat():
    chat = load("TESTDATA_android_24h.txt")
    assert chat.messages[0].when == datetime(2026, 9, 5, 14, 2)
    assert chat.messages[5].when == datetime(2026, 9, 5, 18, 30)
    assert len(chat.messages) == 8 and chat.system_lines == 0


def test_iphone_layout_with_seconds_and_invisible_marks():
    chat = load("TESTDATA_iphone.txt")
    assert chat.messages[0].when == datetime(2026, 10, 18, 21, 15, 30)       # 2-digit year, 9:15:30 PM
    assert chat.messages[0].sender == "Hina"
    assert chat.system_lines == 1 and chat.media_messages == 1               # the encryption notice, one image
    assert not any("end-to-end" in m.text for m in chat.messages)
    assert all(m.text == m.text.strip() and "\u200e" not in m.text for m in chat.messages)


# --- dates ---------------------------------------------------------------------------------------

def test_month_first_dates_are_recognised():
    chat = load("TESTDATA_month_first.txt")
    assert chat.date_order == "mdy" and chat.date_order_ambiguous is False
    assert chat.messages[0].when == datetime(2026, 10, 18, 21, 15)
    assert chat.messages[-1].when == datetime(2026, 10, 19, 1, 0)             # 1:00 AM


def test_when_every_date_fits_both_ways_the_caller_is_told_and_can_choose():
    chat = load("TESTDATA_ambiguous.txt")
    assert chat.date_order == "dmy" and chat.date_order_ambiguous is True    # day first by default
    assert chat.messages[0].when == datetime(2026, 3, 2, 10, 0)
    chosen = load("TESTDATA_ambiguous.txt", date_order="mdy")
    assert chosen.date_order == "mdy" and chosen.date_order_ambiguous is False
    assert chosen.messages[0].when == datetime(2026, 2, 3, 10, 0)


@pytest.mark.parametrize(
    ("dates", "expected"),
    [([(18, 10, 2026)], ("dmy", False)), ([(10, 18, 2026)], ("mdy", False)), ([(2, 3, 2026)], ("dmy", True)),
     ([(2026, 10, 18)], ("ymd", False)), ([(18, 10, 26), (3, 25, 26)], ("dmy", False))],
)
def test_date_order_detection(dates, expected):
    assert detect_date_order(dates) == expected


def test_an_impossible_date_is_counted_not_guessed():
    chat = parse_chat("31/02/2026, 10:00 - Ali: order chahiye\n01/03/2026, 10:00 - Ali: hello")
    assert chat.unreadable_lines == 1 and [m.text for m in chat.messages] == ["hello"]


# --- group chats, file names, bad input ----------------------------------------------------------

def test_group_chat_senders_and_system_lines():
    chat = load("TESTDATA_group.txt")
    assert {name for name, _ in chat.senders} == {"Nida", "Shop", "Farhan"}
    assert chat.system_lines == 2


@pytest.mark.parametrize(
    ("filename", "name"),
    [("WhatsApp Chat with Ayesha Khan.txt", "Ayesha Khan"), ("WhatsApp Chat - Ali.txt", "Ali"),
     ("WhatsApp Chat with Ali (1).txt", "Ali"), ("C:\\Users\\x\\WhatsApp Chat with Sana.txt", "Sana"),
     ("notes.txt", None), (None, None), ("", None)],
)
def test_the_customer_name_from_the_file_name(filename, name):
    assert name_from_filename(filename) == name


@pytest.mark.parametrize("text", ["", "   \n\n", "just some text\nwith no messages", "\x00\x01\x02 binary", "[not a date] hi"])
def test_text_that_is_not_a_chat_gives_no_messages_and_no_error(text):
    chat = parse_chat(text)
    assert chat.messages == [] and chat.senders == []


def test_a_large_chat_is_read_quickly():
    lines = [f"18/10/2026, 9:{i % 60:02d} pm - Ali: hello {i}" for i in range(20000)]
    chat = parse_chat("\n".join(lines))
    assert len(chat.messages) == 20000


# --- privacy -------------------------------------------------------------------------------------

def test_reading_a_chat_logs_nothing_and_writes_no_file(caplog, tmp_path, monkeypatch):
    """A chat is other people's private messages: no part of it may reach the logs or the disk."""
    monkeypatch.chdir(tmp_path)
    text = (FIXTURES / "TESTDATA_android_12h.txt").read_text(encoding="utf-8")
    with caplog.at_level(logging.DEBUG):
        chat = parse_chat(text, "WhatsApp Chat with Ayesha.txt")
        extract_candidates(chat.messages, me="Sana Boutique")
    assert caplog.records == []
    assert list(tmp_path.iterdir()) == []
