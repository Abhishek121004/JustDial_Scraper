"""Data cleaning and deduplication for scraped listings."""

import re

from app.schemas.listing import ListingCreate, RawListing


def strip_text(value: str) -> str:
    return (value or "").strip()


def clean_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 7:
        return ""
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits


def clean_rating(value: str) -> str:
    match = re.search(r"(\d+\.?\d*)", value or "")
    return match.group(1) if match else ""


def clean_reviews(value: str) -> str:
    match = re.search(r"(\d+)", value or "")
    return match.group(1) if match else ""


def make_dedup_key(name: str, phone: str) -> str:
    cleaned_phone = clean_phone(phone)
    prefix = cleaned_phone[:6] if len(cleaned_phone) >= 6 else cleaned_phone
    return strip_text(name).lower() + prefix


def clean_listing(raw: RawListing) -> ListingCreate:
    phone = clean_phone(raw.phone)
    name = strip_text(raw.name)
    return ListingCreate(
        name=name,
        phone=phone,
        email=strip_text(raw.email),
        address=strip_text(raw.address),
        rating=clean_rating(raw.rating),
        reviews=clean_reviews(raw.reviews),
        category=strip_text(raw.category),
        source_url=strip_text(raw.source_url),
        raw_encoded_phone=raw.raw_encoded_phone,
        dedup_key=make_dedup_key(name, phone),
    )


def deduplicate(records: list[ListingCreate]) -> list[ListingCreate]:
    seen: set[str] = set()
    unique: list[ListingCreate] = []
    for record in records:
        if record.dedup_key in seen:
            continue
        seen.add(record.dedup_key)
        unique.append(record)
    return unique


def merge_and_dedupe(
    existing: list[ListingCreate], new: list[ListingCreate]
) -> list[ListingCreate]:
    return deduplicate(existing + new)
