"""CSV export with append and deduplication semantics."""

import csv
from pathlib import Path

from app.schemas.listing import ListingCreate
from app.services.cleaner import deduplicate, merge_and_dedupe
from app.services.url_builder import skill_to_slug

CSV_COLUMNS = [
    "name",
    "phone",
    "email",
    "address",
    "rating",
    "reviews",
    "category",
    "source_url",
]


def csv_filename(skill: str, pincode: str) -> str:
    slug = skill_to_slug(skill).replace("-", "_")
    return f"{slug}_{pincode}.csv"


def csv_path(output_dir: str, skill: str, pincode: str) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path / csv_filename(skill, pincode)


def _listing_to_row(listing: ListingCreate) -> dict[str, str]:
    return {
        "name": listing.name,
        "phone": listing.phone,
        "email": listing.email,
        "address": listing.address,
        "rating": listing.rating,
        "reviews": listing.reviews,
        "category": listing.category,
        "source_url": listing.source_url,
    }


def read_csv(path: Path) -> list[ListingCreate]:
    if not path.exists():
        return []

    records: list[ListingCreate] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = row.get("name", "")
            phone = row.get("phone", "")
            from app.services.cleaner import make_dedup_key

            records.append(
                ListingCreate(
                    name=name,
                    phone=phone,
                    email=row.get("email", ""),
                    address=row.get("address", ""),
                    rating=row.get("rating", ""),
                    reviews=row.get("reviews", ""),
                    category=row.get("category", ""),
                    source_url=row.get("source_url", ""),
                    dedup_key=make_dedup_key(name, phone),
                )
            )
    return records


def write_csv(path: Path, records: list[ListingCreate]) -> int:
    unique = deduplicate(records)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for record in unique:
            writer.writerow(_listing_to_row(record))
    return len(unique)


def export_listings(
    output_dir: str,
    skill: str,
    pincode: str,
    listings: list[ListingCreate],
) -> tuple[Path, int]:
    path = csv_path(output_dir, skill, pincode)
    existing = read_csv(path)
    merged = merge_and_dedupe(existing, listings)
    count = write_csv(path, merged)
    return path, count
