from app.schemas.listing import ListingCreate, RawListing
from app.services.cleaner import (
    clean_listing,
    clean_phone,
    deduplicate,
    make_dedup_key,
    merge_and_dedupe,
    strip_text,
)


def test_strip_whitespace():
    assert strip_text("  hello\n") == "hello"


def test_clean_phone_formats():
    assert clean_phone("(987) 654-3210") == "9876543210"


def test_short_phone_becomes_blank():
    assert clean_phone("12345") == ""


def test_dedup_key_uses_name_and_phone_prefix():
    key = make_dedup_key("Cool Point AC", "9876543210")
    assert key == "cool point ac987654"


def test_deduplicate_keeps_first():
    records = [
        ListingCreate(name="A", phone="9876543210", dedup_key="a987654"),
        ListingCreate(name="A.C.", phone="9876549999", dedup_key="a987654"),
    ]
    result = deduplicate(records)
    assert len(result) == 1
    assert result[0].name == "A"


def test_merge_and_dedupe():
    existing = [ListingCreate(name="Old", phone="9876543210", dedup_key="old987654")]
    new = [
        ListingCreate(name="Old Shop", phone="9876548888", dedup_key="old987654"),
        ListingCreate(name="New", phone="8765432109", dedup_key="new876543"),
    ]
    merged = merge_and_dedupe(existing, new)
    assert len(merged) == 2
    assert merged[0].name == "Old"
    assert merged[1].name == "New"


def test_clean_listing_from_raw():
    raw = RawListing(
        name="  Test Co  ",
        phone="(987) 654-3210",
        rating="4.2 stars",
        reviews="38 Ratings",
    )
    cleaned = clean_listing(raw)
    assert cleaned.name == "Test Co"
    assert cleaned.phone == "9876543210"
    assert cleaned.rating == "4.2"
    assert cleaned.reviews == "38"
