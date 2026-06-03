from unittest.mock import MagicMock, patch

from app.db.models import JobStatus, Listing
from app.schemas.listing import RawListing, ScrapeRequest
from app.services.job_service import JobService
from app.services.scraper import ScrapeResult


def test_captcha_sets_partial_status(db_session):
    scraper = MagicMock()
    scraper.run.return_value = ScrapeResult(
        listings=[
            RawListing(name="Partial Co", phone="9876543210", source_url="http://x.com")
        ],
        pages_scraped=1,
        captcha_encountered=True,
        error_message="CAPTCHA detected — partial results saved",
    )
    service = JobService(db_session, scraper)
    job = service.create_job(ScrapeRequest(pincode="768028", skill="AC Repair"))
    service.run_job_sync(job.id)

    job = service.get_job(job.id)
    assert job.status == JobStatus.PARTIAL.value
    assert db_session.query(Listing).count() == 1


def test_page_load_error_sets_failed_when_no_records(db_session):
    scraper = MagicMock()
    scraper.run.return_value = ScrapeResult(
        listings=[],
        pages_scraped=0,
        error_message="Failed to load page after retries",
    )
    service = JobService(db_session, scraper)
    job = service.create_job(ScrapeRequest(pincode="768028", skill="AC Repair"))
    service.run_job_sync(job.id)

    job = service.get_job(job.id)
    assert job.status == JobStatus.FAILED.value


def test_page_load_error_partial_when_records_exist(db_session):
    scraper = MagicMock()
    scraper.run.return_value = ScrapeResult(
        listings=[
            RawListing(name="Saved Co", phone="9876543210", source_url="http://x.com")
        ],
        pages_scraped=1,
        error_message="Failed to load page after retries",
    )
    service = JobService(db_session, scraper)
    job = service.create_job(ScrapeRequest(pincode="768028", skill="AC Repair"))
    service.run_job_sync(job.id)

    job = service.get_job(job.id)
    assert job.status == JobStatus.PARTIAL.value


def test_invalid_scrape_request_rejected(client):
    response = client.post("/api/v1/scrape", json={"pincode": "12", "skill": ""})
    assert response.status_code == 422


def test_gibberish_phone_stored_with_raw_encoded(db_session):
    scraper = MagicMock()
    scraper.run.return_value = ScrapeResult(
        listings=[
            RawListing(
                name="Broken Phone Listing",
                phone="",
                raw_encoded_phone="xyzinvalid",
                needs_click_fallback=True,
                source_url="http://x.com",
            )
        ],
        pages_scraped=1,
    )
    service = JobService(db_session, scraper)
    job = service.create_job(ScrapeRequest(pincode="768028", skill="AC Repair"))
    service.run_job_sync(job.id)

    listing = db_session.query(Listing).one()
    assert listing.phone == ""
    assert listing.raw_encoded_phone == "xyzinvalid"


@patch("playwright.sync_api.sync_playwright")
def test_scraper_retries_on_failure(mock_playwright):
    page = MagicMock()
    page.goto.side_effect = Exception("timeout")
    page.wait_for_selector.side_effect = Exception("timeout")

    browser = MagicMock()
    context = MagicMock()
    context.new_page.return_value = page
    browser.new_context.return_value = context

    playwright_instance = MagicMock()
    playwright_instance.chromium.launch.return_value = browser
    mock_playwright.return_value.__enter__.return_value = playwright_instance

    from app.services.scraper import ScraperService

    service = ScraperService(retry_count=1, scroll_count=1, min_delay=0, max_delay=0)
    result = service.run("768028", "AC Repair", max_pages=1)

    assert result.error_message is not None
    assert page.goto.call_count == 2
