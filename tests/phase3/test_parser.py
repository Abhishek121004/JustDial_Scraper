from pathlib import Path

import pytest

from app.services.parser import parse_listings

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "html"
SOURCE_URL = "https://www.justdial.com/768028/ac-repair"


@pytest.fixture
def sample_html() -> str:
    return (FIXTURES_DIR / "sample_page.html").read_text(encoding="utf-8")


def test_parse_fixture_returns_three_cards(sample_html):
    listings = parse_listings(sample_html, SOURCE_URL)
    assert len(listings) == 3


def test_parse_encodes_phone_correctly(sample_html):
    listings = parse_listings(sample_html, SOURCE_URL)
    assert listings[0].phone == "9876543210"
    assert listings[0].name == "Cool Point AC Services"
    assert listings[0].address == "Shop 12, MG Road, Bhubaneswar"
    assert listings[0].rating == "4.2"
    assert listings[0].reviews == "38"
    assert listings[0].category == "AC Repair & Service"
    assert listings[0].source_url == SOURCE_URL


def test_missing_fields_stored_as_blank(sample_html):
    listings = parse_listings(sample_html, SOURCE_URL)
    broken = listings[2]
    assert broken.name == "Broken Phone Listing"
    assert broken.address == ""
    assert broken.rating == ""
    assert broken.reviews == ""


def test_malformed_phone_flagged_for_fallback(sample_html):
    listings = parse_listings(sample_html, SOURCE_URL)
    broken = listings[2]
    assert broken.phone == ""
    assert broken.needs_click_fallback is True
    assert broken.raw_encoded_phone == "xyzinvalid"
