"""End-to-end pipeline test using HTML fixture (no browser)."""

from pathlib import Path

import pytest

from app.db.models import JobStatus
from app.schemas.listing import ScrapeRequest
from app.services.cleaner import clean_listing
from app.services.csv_export import read_csv
from app.services.job_service import JobService
from app.services.parser import parse_listings
from app.services.scraper import ScrapeResult
from unittest.mock import MagicMock


FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "html" / "sample_page.html"
SOURCE_URL = "https://www.justdial.com/768028/ac-repair"


def test_fixture_pipeline_parser_cleaner_db_csv(db_session, tmp_path, monkeypatch):
    """Phases 3-4-6 wired together without Playwright."""
    html = FIXTURE.read_text(encoding="utf-8")
    raw_listings = parse_listings(html, SOURCE_URL)
    assert len(raw_listings) == 3

    cleaned = [clean_listing(r) for r in raw_listings]
    assert cleaned[0].phone == "9876543210"
    assert cleaned[2].phone == ""

    scraper = MagicMock()
    scraper.run.return_value = ScrapeResult(listings=raw_listings, pages_scraped=1)

    monkeypatch.setattr("app.services.job_service.settings.output_dir", str(tmp_path))
    service = JobService(db_session, scraper)
    job = service.create_job(ScrapeRequest(pincode="768028", skill="AC Repair"))
    service.run_job_sync(job.id)

    job = service.get_job(job.id)
    assert job.status == JobStatus.COMPLETED.value
    assert job.records_found == 3

    csv_file = tmp_path / "ac_repair_768028.csv"
    assert csv_file.exists()
    rows = read_csv(csv_file)
    assert len(rows) == 3


@pytest.mark.live
def test_live_scrape_one_page():
    """Manual live verification — skipped in CI by default."""
    from app.services.scraper import ScraperService

    service = ScraperService(headless=True, min_delay=0, max_delay=0, scroll_count=2)
    result = service.run("768028", "AC Repair", max_pages=1)
    assert result.pages_scraped >= 0
