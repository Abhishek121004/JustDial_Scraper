from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.listing import RawListing
from app.services.scraper import ScraperService
from app.services.url_builder import build_search_url

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "html"


@pytest.fixture
def sample_html() -> str:
    return (FIXTURES_DIR / "sample_page.html").read_text(encoding="utf-8")


class TestScraperService:
    def test_build_url_sequence(self):
        urls = [build_search_url("768028", "AC Repair", p) for p in range(1, 4)]
        assert urls[0].endswith("/768028/ac-repair")
        assert urls[1].endswith("/page-2")
        assert urls[2].endswith("/page-3")

    def test_detect_captcha(self):
        service = ScraperService()
        assert service._detect_captcha("<html>captcha form</html>") is True
        assert service._detect_captcha("<html>normal page</html>") is False

    @patch("playwright.sync_api.sync_playwright")
    @patch("app.services.scraper.time.sleep")
    def test_run_stops_on_empty_page(self, _sleep, mock_playwright, sample_html):
        page = MagicMock()
        page.content.side_effect = [sample_html, "<html><body></body></html>"]
        page.locator.return_value.count.return_value = 0

        browser = MagicMock()
        context = MagicMock()
        context.new_page.return_value = page
        browser.new_context.return_value = context

        playwright_instance = MagicMock()
        playwright_instance.chromium.launch.return_value = browser
        mock_playwright.return_value.__enter__.return_value = playwright_instance

        service = ScraperService(scroll_count=2, min_delay=0, max_delay=0, retry_count=0)
        result = service.run("768028", "AC Repair", max_pages=5)

        assert result.pages_scraped == 1
        assert len(result.listings) == 3
        assert page.goto.call_count == 2

    @patch("playwright.sync_api.sync_playwright")
    def test_run_detects_captcha(self, mock_playwright):
        page = MagicMock()
        page.content.return_value = "<html><body>recaptcha challenge</body></html>"

        browser = MagicMock()
        context = MagicMock()
        context.new_page.return_value = page
        browser.new_context.return_value = context

        playwright_instance = MagicMock()
        playwright_instance.chromium.launch.return_value = browser
        mock_playwright.return_value.__enter__.return_value = playwright_instance

        service = ScraperService(retry_count=0)
        result = service.run("768028", "AC Repair", max_pages=1)

        assert result.captcha_encountered is True
        assert result.error_message is not None

    @patch("app.services.scraper.parse_listings")
    @patch("playwright.sync_api.sync_playwright")
    def test_scraper_calls_parser(self, mock_playwright, mock_parse, sample_html):
        mock_parse.return_value = [
            RawListing(name="Test", phone="9876543210", source_url="http://example.com")
        ]

        page = MagicMock()
        page.content.return_value = sample_html

        browser = MagicMock()
        context = MagicMock()
        context.new_page.return_value = page
        browser.new_context.return_value = context

        playwright_instance = MagicMock()
        playwright_instance.chromium.launch.return_value = browser
        mock_playwright.return_value.__enter__.return_value = playwright_instance

        service = ScraperService(retry_count=0, scroll_count=1, min_delay=0, max_delay=0)
        service.run("768028", "AC Repair", max_pages=1)

        mock_parse.assert_called()
