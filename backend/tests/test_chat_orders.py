"""Finding orders in a chat with simple rules. Every chat here is made up (tests/fixtures/whatsapp)."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.services.chat_orders import message_facts, extract_candidates
from app.services.pk_cities import find_cities
from app.services.whatsapp_chat import Message, parse_chat
from tests.test_whatsapp_chat import FIXTURES


def candidates(name: str, me: str | None = None, **kw):
    chat = parse_chat((FIXTURES / name).read_text(encoding="utf-8"), **kw)
    return extract_candidates(chat.messages, me=me)


def amounts(text: str):
    return [(str(v), total) for v, total in message_facts(text).amounts]


# --- amounts ---------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text", ["Rs 2500", "Rs. 2500", "rs2500", "Rs.2,500", "PKR 2500", "pkr 2,500", "2500/-", "2,500 /-",
             "2500 rupay", "2500 rupees", "2500 rupaye", "2500 Rs", "٢٥٠٠ Rs", "Rs ٢٥٠٠", "total Rs 2500 only"],
)
def test_every_usual_way_of_writing_an_amount(text):
    assert [v for v, _ in amounts(text)] == ["2500"]


def test_amounts_with_paisa_and_several_in_one_message():
    assert [v for v, _ in amounts("Rs 1500.50 aur delivery 200/-")] == ["1500", "200"]      # paisa are dropped
    assert [v for v, _ in amounts("suit 2500/- aur scarf Rs 800")] == ["2500", "800"]


def test_a_total_is_marked_as_a_total():
    assert amounts("Total Rs. 4,500 hoga") == [("4500", True)]
    assert amounts("kul bill 3200 rupay") == [("3200", True)]
    assert amounts("price Rs 900") == [("900", False)]


@pytest.mark.parametrize("text", ["Rs 5", "I have 2 suits", "order 123", "size 38", "kal 5 baje", "0300 1234567", "year 2026"])
def test_numbers_that_are_not_amounts_are_ignored(text):
    assert message_facts(text).amounts == ()


# --- phone numbers ---------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    ["0300-1234567", "0300 1234567", "03001234567", "+92 300 1234567", "+923001234567", "923001234567",
     "0092 300 1234567", "3001234567", "0300 123 4567", "call me on 0300-1234567 please", "My number: 0300 1234567."],
)
def test_every_usual_way_of_writing_a_phone_number(text):
    assert message_facts(text).phones == ("+923001234567",)


def test_two_numbers_and_numbers_that_are_not_phones():
    assert message_facts("0300 1111111 or 0345 2222222").phones == ("+923001111111", "+923452222222")
    for text in ["042 35761234", "Rs 2500", "order 12345", "+44 7911 123456", "20261018"]:
        assert message_facts(text).phones == (), text


def test_a_phone_number_is_never_also_an_amount():
    facts = message_facts("0300 1234567 Rs 4500")
    assert facts.phones == ("+923001234567",) and [str(v) for v, _ in facts.amounts] == ["4500"]


# --- order words and cities ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    ["I want to order this", "ORDER", "please confirm", "book kar do", "bhej do", "bhej dein jaldi", "mujhe ye chahiye",
     "chaiye", "COD", "cash on delivery", "آرڈر", "کنفرم"],
)
def test_strong_order_words_in_english_and_roman_urdu(text):
    assert message_facts(text).strong is True


@pytest.mark.parametrize("text", ["kitne ka hai", "what is the address", "delivery kab hogi", "price?"])
def test_weak_words_alone_are_not_an_order_request(text):
    facts = message_facts(text)
    assert facts.weak is True and facts.strong is False


@pytest.mark.parametrize("text", ["hello", "thanks", "border", "recorder", "booking"[:0] + "ok", "salam"])
def test_no_order_words(text):
    facts = message_facts(text)
    assert not facts.strong and not facts.weak


def test_payment_hints():
    assert message_facts("COD karna hai").cod and not message_facts("COD karna hai").prepaid
    assert message_facts("advance easypaisa kar diya").prepaid and message_facts("payment done").prepaid
    assert not message_facts("hello").cod and not message_facts("hello").prepaid


@pytest.mark.parametrize(
    ("text", "cities"),
    [("Lahore", ["Lahore"]), ("send to LAHORE", ["Lahore"]), ("pindi", ["Rawalpindi"]), ("Karachi aur Multan", ["Karachi", "Multan"]),
     ("Dera Ghazi Khan", ["Dera Ghazi Khan"]), ("nothing here", []), ("Lahoreshire", []), ("Rawalpindi", ["Rawalpindi"])],
)
def test_cities(text, cities):
    assert find_cities(text) == cities


# --- finding orders in the test chats -----------------------------------------------------------------

def test_android_chat_finds_both_orders_with_what_was_found():
    first, second = candidates("TESTDATA_android_12h.txt", me="Sana Boutique")
    assert (first.customer_name, first.phone, first.city, first.amount) == ("Ayesha", "+923001234567", "Lahore", Decimal(4500))
    assert first.payment_type == "cod" and first.order_date == date(2026, 10, 18)
    assert (first.confidence, first.confidence_label) == ("high", "Amount and phone found")
    assert first.found == {"amount": True, "phone": True, "keyword": True, "city": True}
    assert (second.customer_name, second.phone, second.amount) == ("Bilal", None, Decimal(2500))
    assert (second.confidence, second.confidence_label) == ("medium", "Only amount found")


def test_the_chosen_total_wins_over_other_amounts():
    # "Rs 200 delivery" appears too, but the amount marked "total" is the order amount.
    chat = parse_chat("18/10/2026, 9:00 pm - Ali: order chahiye 0300 1234567\n18/10/2026, 9:01 pm - Shop: delivery Rs 200, total Rs 3,400")
    (found,) = extract_candidates(chat.messages, me="Shop")
    assert found.amount == Decimal(3400) and found.other_amounts == [Decimal(200)]


def test_one_order_spread_over_messages_is_one_candidate_and_two_customers_are_two():
    zara, imran = candidates("TESTDATA_android_24h.txt", me="Shop")
    assert (zara.customer_name, zara.phone, zara.city, zara.amount, zara.payment_type) == ("Zara", "+923219876543", "Karachi", Decimal(1800), "prepaid")
    assert (imran.customer_name, imran.phone, imran.city, imran.amount, imran.payment_type) == ("Imran", "+923451112223", "Multan", Decimal(6000), "cod")
    assert len(zara.messages) == 5 and zara.order_time == datetime(2026, 9, 5, 14, 2)


def test_iphone_chat():
    (hina,) = candidates("TESTDATA_iphone.txt", me="Shop")
    assert (hina.phone, hina.amount, hina.city, hina.order_date) == ("+923331234567", Decimal(3200), "Islamabad", date(2026, 10, 18))


def test_month_first_chat_dates_and_the_sellers_own_words_do_not_make_an_order():
    only = candidates("TESTDATA_month_first.txt", me="Shop")
    assert [c.customer_name for c in only] == ["Omar"] and only[0].order_date == date(2026, 10, 18)
    # Without knowing who the seller is, "confirmed" alone looks like a (low confidence) request.
    assert [c.confidence for c in candidates("TESTDATA_month_first.txt")] == ["high", "low"]


def test_group_chat_keeps_customers_apart():
    nida, farhan = candidates("TESTDATA_group.txt")
    assert (nida.customer_name, nida.phone, nida.city, nida.amount) == ("Nida", "+923005550001", "Peshawar", Decimal(900))
    assert (farhan.customer_name, farhan.phone, farhan.city, farhan.amount, farhan.payment_type) == ("Farhan", "+923335550002", "Quetta", Decimal(4200), "cod")


def test_the_date_choice_changes_the_order_date():
    assert candidates("TESTDATA_ambiguous.txt")[0].order_date == date(2026, 3, 2)
    assert candidates("TESTDATA_ambiguous.txt", date_order="mdy")[0].order_date == date(2026, 2, 3)


def test_a_new_phone_number_in_the_same_minutes_starts_another_order():
    chat = parse_chat("\n".join([
        "18/10/2026, 9:00 pm - Ali: order Rs 1000 0300 1111111",
        "18/10/2026, 9:03 pm - Bina: order Rs 2000 0345 2222222",
    ]))
    first, second = extract_candidates(chat.messages)
    assert (first.phone, first.amount, second.phone, second.amount) == ("+923001111111", Decimal(1000), "+923452222222", Decimal(2000))


def test_the_customers_name_comes_from_the_file_name_or_the_saved_number():
    chat = parse_chat("18/10/2026, 9:00 pm - +92 300 1234567: order chahiye Rs 900", "WhatsApp Chat with +92 300 1234567.txt")
    (found,) = extract_candidates(chat.messages, customer_name_hint=chat.customer_name_hint)
    assert found.customer_name == "" and found.phone == "+923001234567"        # a number is not a name

    chat = parse_chat("18/10/2026, 9:00 pm - Ali: order chahiye\n18/10/2026, 9:01 pm - Me: ok", "WhatsApp Chat with Ali.txt")
    (found,) = extract_candidates(chat.messages, me="Me", customer_name_hint=chat.customer_name_hint)
    assert found.customer_name == "Ali" and found.confidence_label == "Only keyword found"


def test_chat_that_is_not_about_orders_gives_nothing():
    chat = parse_chat("\n".join(f"18/10/2026, 9:{i:02d} pm - Ali: haha ok good morning {i}" for i in range(30)))
    assert extract_candidates(chat.messages) == []


def test_long_messages_and_long_conversations_are_cut_for_the_review_screen():
    lines = [f"18/10/2026, 9:{i:02d} pm - Ali: order Rs 100{i} " + "x" * 600 for i in range(12)]
    (found,) = extract_candidates(parse_chat("\n".join(lines)).messages)
    assert len(found.messages) == 8 and all(len(m.text) <= 400 for m in found.messages)


def test_candidates_are_numbered_in_time_order():
    found = candidates("TESTDATA_android_24h.txt", me="Shop")
    assert [c.id for c in found] == [0, 1] and found[0].order_time < found[1].order_time


def test_no_messages_no_candidates():
    assert extract_candidates([]) == []
    assert extract_candidates([Message(0, datetime(2026, 1, 1), "Ali", "hi")]) == []
