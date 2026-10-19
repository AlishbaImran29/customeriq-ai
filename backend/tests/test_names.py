"""One spelling for each courier and city. The names here are the usual ones; no real data is used."""

import json

import pytest

from app.services.names import (
    CITY_NAMES, COURIERS, NameMappingError, Normaliser, load_cities, load_couriers, normalise_city, normalise_courier,
)


@pytest.mark.parametrize(
    "typed",
    ["TCS", "tcs", "tcs ", "  Tcs", "T.C.S", "t c s", "T-C-S", "TCS Express", "tcs courier"],
)
def test_every_way_of_writing_tcs_is_one_courier(typed):
    result = normalise_courier(typed)
    assert result.name == "TCS" and result.known is True and result.raw == typed.strip()


@pytest.mark.parametrize(
    ("typed", "expected"),
    [("leopards", "Leopards"), ("Leopard Courier", "Leopards"), ("M&P", "M&P"), ("m and p", "M&P"), ("M & P express", "M&P"),
     ("post ex", "PostEx"), ("BLUE-EX", "BlueEX"), ("callcourier", "Call Courier"), ("pakpost", "Pakistan Post"), ("DHL Express", "DHL")],
)
def test_other_couriers_and_their_spellings(typed, expected):
    assert normalise_courier(typed).name == expected


@pytest.mark.parametrize(
    ("typed", "expected"),
    [("Isb", "Islamabad"), ("islamabad", "Islamabad"), ("ISLAMABAD ", "Islamabad"), ("ISLO", "Islamabad"), ("pindi", "Rawalpindi"),
     ("RWP", "Rawalpindi"), ("khi", "Karachi"), ("lhr", "Lahore"), ("D.G. Khan", "Dera Ghazi Khan"), ("dg khan", "Dera Ghazi Khan"),
     ("Multan", "Multan"), ("lyallpur", "Faisalabad"), ("Wah Cantt", "Wah Cantt")],
)
def test_cities_and_their_short_forms(typed, expected):
    result = normalise_city(typed)
    assert result.name == expected and result.known is True


def test_a_name_that_is_not_in_the_list_is_kept_tidied_up_and_marked_new():
    courier = normalise_courier("  fast   rider  express ")
    assert (courier.name, courier.known, courier.raw) == ("Fast Rider Express", False, "fast   rider  express")
    assert normalise_courier("DHL").known is True
    city = normalise_city("new city  town")
    assert (city.name, city.known) == ("New City Town", False)
    assert normalise_courier("xyz").name == "Xyz" and normalise_courier("ABCD").name == "ABCD"     # a short all-capital word is an acronym


@pytest.mark.parametrize("blank", [None, "", "   ", "\t"])
def test_blank_gives_none(blank):
    assert normalise_courier(blank) is None and normalise_city(blank) is None


def test_the_shipped_lists_are_valid_and_cover_their_own_names():
    assert load_couriers().names and load_cities().names
    for name in COURIERS.names:
        assert normalise_courier(name).name == name
    for name in CITY_NAMES.names:
        assert normalise_city(name).name == name


def test_the_list_can_be_edited_by_the_seller(tmp_path):
    path = tmp_path / "couriers.json"
    path.write_text(json.dumps({"couriers": {"TCS": ["tcs"], "My Rider": ["myrider", "m rider"]}}), encoding="utf-8")
    edited = load_couriers(path)
    assert edited.normalise("M.Rider").name == "My Rider" and edited.normalise("tcs").name == "TCS"
    assert edited.normalise("Leopards").known is False                                       # not in THIS list


def test_a_spelling_given_to_two_names_is_refused():
    with pytest.raises(NameMappingError) as error:
        Normaliser({"TCS": ["express"], "Leopards": ["express"]})
    assert "express" in str(error.value)
    with pytest.raises(NameMappingError):
        Normaliser({"TCS": ["..."]})                                                         # a spelling with no letters


def test_all_the_cities_the_chat_import_knows_are_known_here():
    from app.services.pk_cities import CITIES

    assert all(normalise_city(c).known for c in CITIES)
