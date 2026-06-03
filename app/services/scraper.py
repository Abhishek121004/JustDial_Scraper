"""Playwright-based browser scraper orchestration."""

import logging
import random
import re
import time
from dataclasses import dataclass, field

from app.config import settings
from app.schemas.listing import RawListing
from app.services.exceptions import CaptchaError, PageLoadError
from app.services.parser import parse_listings
from app.services.url_builder import build_search_url

logger = logging.getLogger(__name__)

CARD_WAIT_SELECTOR = "div.listing-card, li.resultbox, div.store-details, .cntanr"
CAPTCHA_MARKERS = ("captcha", "recaptcha", "verify you are human")
GET_NUMBER_SELECTOR = "a.callcontent, .callNow, span.mobilesv"


@dataclass
class ScrapeResult:
    listings: list[RawListing] = field(default_factory=list)
    pages_scraped: int = 0
    captcha_encountered: bool = False
    error_message: str | None = None


class ScraperService:
    def __init__(
        self,
        headless: bool | None = None,
        scroll_count: int | None = None,
        min_delay: float | None = None,
        max_delay: float | None = None,
        retry_count: int | None = None,
        page_timeout_ms: int | None = None,
    ):
        self.headless = headless if headless is not None else settings.headless
        self.scroll_count = scroll_count if scroll_count is not None else settings.scroll_count
        self.min_delay = min_delay if min_delay is not None else settings.min_delay
        self.max_delay = max_delay if max_delay is not None else settings.max_delay
        self.retry_count = retry_count if retry_count is not None else settings.retry_count
        self.page_timeout_ms = (
            page_timeout_ms if page_timeout_ms is not None else settings.page_timeout_ms
        )

    def run(
        self,
        pincode: str,
        skill: str,
        max_pages: int | None = None,
        job_id: str | None = None,
    ) -> ScrapeResult:
        max_pages = max_pages or settings.max_pages
        result = ScrapeResult()

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            result.error_message = "Playwright is not installed"
            raise PageLoadError(result.error_message) from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=self.headless,
                args=["--disable-http2"]
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            page.set_default_timeout(self.page_timeout_ms)

            try:
                for page_num in range(1, max_pages + 1):
                    url = build_search_url(pincode, skill, page_num)
                    logger.info("job=%s scraping page=%s url=%s", job_id, page_num, url)

                    try:
                        html = self._load_page_with_retry(page, url, job_id)
                    except PageLoadError as exc:
                        result.error_message = str(exc)
                        break

                    if self._detect_captcha(html):
                        result.captcha_encountered = True
                        raise CaptchaError("CAPTCHA detected — stopping scrape")

                    source_url = url
                    listings = parse_listings(html, source_url)
                    self._apply_phone_fallback(page, listings)

                    if not listings:
                        logger.info("job=%s no results on page=%s — stopping", job_id, page_num)
                        break

                    result.listings.extend(listings)
                    result.pages_scraped = page_num

                    if page_num < max_pages:
                        delay = random.uniform(self.min_delay, self.max_delay)
                        time.sleep(delay)

            except CaptchaError:
                result.error_message = "CAPTCHA detected — partial results saved"
            except PageLoadError as exc:
                result.error_message = str(exc)
            finally:
                browser.close()

        return result

    def _load_page_with_retry(self, page, url: str, job_id: str | None) -> str:
        last_error: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_selector(CARD_WAIT_SELECTOR, timeout=self.page_timeout_ms)
                self._scroll_page(page)
                return page.content()
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "job=%s page load attempt=%s failed: %s", job_id, attempt + 1, exc
                )
                if attempt < self.retry_count:
                    time.sleep(2)
                    continue
        raise PageLoadError(f"Failed to load page after retries: {last_error}")

    def _scroll_page(self, page) -> None:
        for _ in range(self.scroll_count):
            page.evaluate("window.scrollBy(0, window.innerHeight)")
            time.sleep(0.5)

    def _detect_captcha(self, html: str) -> bool:
        lowered = html.lower()
        return any(marker in lowered for marker in CAPTCHA_MARKERS)

    def _apply_phone_fallback(self, page, listings: list[RawListing]) -> None:
        for listing in listings:
            if not listing.needs_click_fallback:
                continue
            try:
                phone = self._click_get_number(page, listing.name)
                if phone:
                    listing.phone = phone
                    listing.needs_click_fallback = False
            except Exception as exc:
                logger.warning("Phone fallback failed for %s: %s", listing.name, exc)

    def _click_get_number(self, page, business_name: str) -> str:
        buttons = page.locator(GET_NUMBER_SELECTOR)
        count = buttons.count()
        for i in range(count):
            card = page.locator(CARD_WAIT_SELECTOR).nth(i)
            if business_name.lower() in (card.inner_text() or "").lower():
                buttons.nth(i).click()
                page.wait_for_timeout(1500)
                text = page.locator(".callcontent, .mobilesv").nth(i).inner_text()
                digits = re.sub(r"\D", "", text or "")
                if len(digits) >= 10:
                    return digits[-10:]
        return ""
