"""HTML parser for JustDial listing cards."""

import re

from bs4 import BeautifulSoup

from app.schemas.listing import RawListing
from app.services.cipher import decode_phone, is_valid_indian_phone

CARD_SELECTOR = "div.listing-card, li.resultbox, div.store-details"
NAME_SELECTOR = ".lng_cont_name, .store-name, h4.lng_cont_name"
PHONE_SELECTOR = ".contact-number, span.mobilesv, .callcontent"
ADDRESS_SELECTOR = ".cont_fl_addr, .mrehit, .address"
RATING_SELECTOR = ".green-box, .rating, span.rating"
REVIEWS_SELECTOR = ".rating_text, .rt_count"
CATEGORY_SELECTOR = ".jcn, .category, .catname"


def _text(element) -> str:
    if element is None:
        return ""
    return element.get_text(strip=True)


def _extract_reviews(text: str) -> str:
    match = re.search(r"(\d+)", text or "")
    return match.group(1) if match else ""


def _extract_rating(text: str) -> str:
    match = re.search(r"(\d+\.?\d*)", text or "")
    return match.group(1) if match else ""


def _parse_phone(encoded_text: str) -> tuple[str, str | None, bool]:
    raw = encoded_text.strip()
    decoded = decode_phone(raw)
    if is_valid_indian_phone(decoded):
        return decoded, raw if raw else None, False
    return "", raw if raw else None, bool(raw)


def parse_listings(html: str, source_url: str) -> list[RawListing]:
    """Parse business listings from a JustDial results page HTML."""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(CARD_SELECTOR)
    if not cards:
        cards = soup.select("[data-id], .cntanr")

    listings: list[RawListing] = []
    for card in cards:
        name = _text(card.select_one(NAME_SELECTOR))
        if not name:
            continue

        phone_el = card.select_one(PHONE_SELECTOR)
        encoded_phone = _text(phone_el)
        phone, raw_encoded, needs_fallback = _parse_phone(encoded_phone)

        address = _text(card.select_one(ADDRESS_SELECTOR))
        rating = _extract_rating(_text(card.select_one(RATING_SELECTOR)))
        reviews = _extract_reviews(_text(card.select_one(REVIEWS_SELECTOR)))
        category = _text(card.select_one(CATEGORY_SELECTOR))

        listings.append(
            RawListing(
                name=name,
                phone=phone,
                email="",
                address=address,
                rating=rating,
                reviews=reviews,
                category=category,
                source_url=source_url,
                raw_encoded_phone=raw_encoded,
                needs_click_fallback=needs_fallback,
            )
        )

    return listings
