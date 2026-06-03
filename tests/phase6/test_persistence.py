from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.db.models import JobStatus, Listing
from app.schemas.listing import ListingCreate, RawListing, ScrapeRequest
from app.services.csv_export import CSV_COLUMNS, export_listings, read_csv
from app.services.job_service import JobService
from app.services.scraper import ScrapeResult


@pytest.fixture
def mock_scraper(sample_html):
    scraper = MagicMock()
    scraper.run.return_value = ScrapeResult(
        listings=[
            RawListing(
                name="Cool Point AC Services",
                phone="9876543210",
                address="Shop 12",
                rating="4.2",
                reviews="38",
                category="AC Repair",
                source_url="https://www.justdial.com/768028/ac-repair",
            )
        ],
        pages_scraped=1,
    )
    return scraper


@pytest.fixture
def sample_html():
    return (Path(__file__).resolve().parent.parent / "fixtures" / "html" / "sample_page.html").read_text(
        encoding="utf-8"
    )


def test_persist_listings(db_session, mock_scraper):
    service = JobService(db_session, mock_scraper)
    job = service.create_job(ScrapeRequest(pincode="768028", skill="AC Repair"))
    service.run_job_sync(job.id, max_pages=1)

    job = service.get_job(job.id)
    assert job.status == JobStatus.COMPLETED.value
    assert job.records_found == 1

    listings = db_session.query(Listing).all()
    assert len(listings) == 1
    assert listings[0].name == "Cool Point AC Services"


def test_dedup_on_rerun(db_session, mock_scraper):
    service = JobService(db_session, mock_scraper)
    job1 = service.create_job(ScrapeRequest(pincode="768028", skill="AC Repair"))
    service.run_job_sync(job1.id, max_pages=1)

    job2 = service.create_job(ScrapeRequest(pincode="768028", skill="AC Repair"))
    service.run_job_sync(job2.id, max_pages=1)

    listings = db_session.query(Listing).all()
    assert len(listings) == 1


def test_csv_export(tmp_path, db_session, mock_scraper, monkeypatch):
    monkeypatch.setattr("app.services.job_service.settings.output_dir", str(tmp_path))
    service = JobService(db_session, mock_scraper)
    job = service.create_job(ScrapeRequest(pincode="768028", skill="AC Repair"))
    service.run_job_sync(job.id, max_pages=1)

    csv_file = tmp_path / "ac_repair_768028.csv"
    assert csv_file.exists()

    rows = read_csv(csv_file)
    assert len(rows) == 1
    assert rows[0].phone == "9876543210"


def test_csv_merge_on_second_export(tmp_path):
    output_dir = str(tmp_path)
    first = [
        ListingCreate(
            name="A",
            phone="9876543210",
            dedup_key="a987654",
            source_url="url1",
        )
    ]
    second = [
        ListingCreate(
            name="A Shop",
            phone="9876549999",
            dedup_key="a987654",
            source_url="url2",
        ),
        ListingCreate(
            name="B",
            phone="8765432109",
            dedup_key="b876543",
            source_url="url3",
        ),
    ]

    path1, count1 = export_listings(output_dir, "AC Repair", "768028", first)
    path2, count2 = export_listings(output_dir, "AC Repair", "768028", second)

    assert path1 == path2
    assert count1 == 1
    assert count2 == 2

    rows = read_csv(path2)
    assert len(rows) == 2
    assert {row.name for row in rows} == {"A", "B"}


def test_job_status_transitions(db_session):
    scraper = MagicMock()
    scraper.run.return_value = ScrapeResult(listings=[], pages_scraped=0, error_message="Failed")
    service = JobService(db_session, scraper)
    job = service.create_job(ScrapeRequest(pincode="768028", skill="AC Repair"))
    service.run_job_sync(job.id)

    job = service.get_job(job.id)
    assert job.status == JobStatus.FAILED.value
