"""Channels: free text from files and sellers becomes one of five fixed channels."""

import pytest

from app.services.channels import CHANNELS, normalise_channel


@pytest.mark.parametrize(
    ("typed", "channel"),
    [
        ("instagram", "instagram"), ("Instagram DM", "instagram"), ("insta", "instagram"), ("IG", "instagram"),
        ("whatsapp", "whatsapp"), ("WhatsApp", "whatsapp"), ("whats app", "whatsapp"), ("wa", "whatsapp"),
        ("facebook", "facebook"), ("Facebook page", "facebook"), ("FB", "facebook"), ("face book", "facebook"),
        ("website", "website"), ("Shopify (web)", "website"), ("Shopify", "website"), ("WooCommerce", "website"),
        ("Magento", "website"), ("Online retail", "website"),
    ],
)
def test_known_channels_in_common_spellings(typed, channel):
    assert normalise_channel(typed) == channel


@pytest.mark.parametrize("typed", [None, "", "   ", "Daraz", "walk-in", "Swan", "phone call"])
def test_anything_else_is_other_and_never_guessed(typed):
    assert normalise_channel(typed) == "other"


def test_the_result_is_always_one_of_the_five():
    for text in ("insta", "wa", "fb", "shopify", "stall", None):
        assert normalise_channel(text) in CHANNELS
    assert CHANNELS == ("instagram", "whatsapp", "facebook", "website", "other")
