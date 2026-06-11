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
from app.services.proxy_manager import ProxyManager
from app.services.url_builder import build_search_url
import json

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
        proxy_urls: list[str] | None = None,
    ):
        self.headless = headless if headless is not None else settings.headless
        self.scroll_count = scroll_count if scroll_count is not None else settings.scroll_count
        self.min_delay = min_delay if min_delay is not None else settings.min_delay
        self.max_delay = max_delay if max_delay is not None else settings.max_delay
        self.retry_count = retry_count if retry_count is not None else settings.retry_count
        self.page_timeout_ms = (
            page_timeout_ms if page_timeout_ms is not None else settings.page_timeout_ms
        )
        # Build proxy manager from explicit list, env PROXY_LIST, or legacy PROXY_URL
        self.proxy_manager: ProxyManager | None = ProxyManager.from_config(
            proxy_list_str=",".join(proxy_urls) if proxy_urls else settings.proxy_list,
            single_proxy=settings.proxy_url if not proxy_urls else None,
        )
        if self.proxy_manager:
            logger.info("Proxy rotation enabled")
        else:
            logger.info("No proxies configured — running without proxy")

    def run(
        self,
        pincode: str,
        skill: str,
        max_pages: int | None = None,
        job_id: str | None = None,
        headless: bool | None = None,
    ) -> ScrapeResult:
        max_pages = max_pages or settings.max_pages
        effective_headless = self.headless if headless is None else headless
        result = ScrapeResult()

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            result.error_message = "Playwright is not installed"
            raise PageLoadError(result.error_message) from exc

        with sync_playwright() as playwright:
            launch_kwargs = {
                "headless": effective_headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-http2",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--no-first-run",
                    "--no-zygote",
                    "--disable-gpu",
                    "--window-size=1366,768",
                    "--lang=en-IN",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            }

            # ------------------------------------------------------------------
            # Proxy selection — per-job proxy (single browser instance)
            # A new browser context is created per page if rotate_per_page=True
            # ------------------------------------------------------------------
            job_proxy = self._pick_proxy() if not settings.proxy_rotate_per_page else None
            if job_proxy:
                launch_kwargs["proxy"] = job_proxy
                logger.info("job=%s using proxy: %s", job_id, job_proxy.get("server"))

            browser = playwright.chromium.launch(**launch_kwargs)

            try:
                for page_num in range(1, max_pages + 1):
                    logger.info("job=%s scraping page=%s", job_id, page_num)

                    # Per-page proxy rotation: create a new context with a fresh proxy
                    if settings.proxy_rotate_per_page and self.proxy_manager:
                        page_proxy = self._pick_proxy()
                        context = self._build_context(browser, proxy=page_proxy)
                        if page_proxy:
                            logger.info(
                                "job=%s page=%s proxy=%s",
                                job_id, page_num, page_proxy.get("server"),
                            )
                    else:
                        page_proxy = job_proxy
                        context = self._build_context(browser, proxy=None)

                    page = context.new_page()
                    page.set_default_timeout(self.page_timeout_ms)

                    try:
                        if page_num == 1 and not effective_headless:
                            # Headed mode only: use human-like homepage form interaction
                            html, status, actual_url = self._search_on_homepage(page, skill, pincode)
                            logger.info("job=%s search status=%s url=%s", job_id, status, actual_url)
                            if status != "ok":
                                raise PageLoadError(f"Homepage search failed: {status}")
                        else:
                            # Headless mode (or page > 1): skip the slow homepage load.
                            url = build_search_url(pincode, skill, page_num)
                            logger.info("job=%s scraping page=%s url=%s", job_id, page_num, url)
                            html = self._load_page_with_retry(page, url, job_id, page_proxy)
                            actual_url = url

                        # Report proxy success
                        if page_proxy and self.proxy_manager:
                            proxy_url_str = self._proxy_dict_to_url(page_proxy)
                            self.proxy_manager.report_success(proxy_url_str)

                    except PageLoadError as exc:
                        # Report proxy failure
                        if page_proxy and self.proxy_manager:
                            proxy_url_str = self._proxy_dict_to_url(page_proxy)
                            self.proxy_manager.report_failure(proxy_url_str)
                        result.error_message = str(exc)
                        context.close()
                        break

                    if self._detect_captcha(html):
                        result.captcha_encountered = True
                        context.close()
                        raise CaptchaError("CAPTCHA detected — stopping scrape")

                    source_url = actual_url if page_num == 1 else url
                    listings = parse_listings(html, source_url)
                    self._apply_phone_fallback(page, listings)
                    print("Listings count:", len(listings))
                    print("Source URL:", source_url)
                    print(html[:1000])

                    context.close()

                    if not listings:
                        logger.info("job=%s no results on page=%s — stopping", job_id, page_num)
                        # Save debug HTML so we can inspect what JustDial returned
                        try:
                            debug_path = f"debug_headless_page{page_num}.html"
                            with open(debug_path, "w", encoding="utf-8") as f:
                                f.write(html)
                            logger.info("job=%s saved debug HTML to %s", job_id, debug_path)
                        except Exception:
                            pass
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

    # ------------------------------------------------------------------
    # Browser / Context helpers
    # ------------------------------------------------------------------

    def _build_context(self, browser, proxy: dict | None):
        """Create a new browser context with anti-detection patches."""
        ctx_kwargs = dict(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        if proxy:
            ctx_kwargs["proxy"] = proxy
        context = browser.new_context(**ctx_kwargs)
        context.add_init_script(
            """
            // Hide webdriver flag
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            // Spoof languages and plugins
            Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            // Spoof chrome runtime (missing in headless)
            window.chrome = window.chrome || { runtime: {} };
            // Spoof permissions API (headless returns denied by default)
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters)
            );
            // Mask headless in User-Agent client hints
            Object.defineProperty(navigator, 'userAgentData', { get: () => undefined });
            """
        )
        return context

    def _pick_proxy(self) -> dict | None:
        """Pick the next proxy from the manager (round-robin)."""
        if not self.proxy_manager:
            return None
        return self.proxy_manager.get_proxy()

    @staticmethod
    def _proxy_dict_to_url(proxy: dict) -> str:
        """Reconstruct a proxy URL string from a Playwright proxy dict for reporting."""
        server = proxy.get("server", "")
        user = proxy.get("username", "")
        pwd = proxy.get("password", "")
        if user and pwd:
            from urllib.parse import urlparse, urlunparse
            p = urlparse(server)
            netloc = f"{user}:{pwd}@{p.hostname}:{p.port}"
            return urlunparse(p._replace(netloc=netloc))
        return server

    # ------------------------------------------------------------------
    # Page loading
    # ------------------------------------------------------------------

    def _load_page_with_retry(
        self,
        page,
        url: str,
        job_id: str | None,
        proxy: dict | None = None,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                # Wait for DOM to be ready instead of `networkidle` which can hang
                # on pages with long-polling or dynamic resources.
                # Cap at 60s — 120s caused 2-minute hangs in headless mode.
                goto_timeout = max(self.page_timeout_ms, 60000)
                page.goto(url, wait_until="domcontentloaded", timeout=goto_timeout)
                page.wait_for_timeout(3000)
                # Try to wait for listing cards — but don't fail if they don't appear.
                # In headless mode JustDial may serve a page with no cards; we still
                # want to return the HTML so the parser can inspect it (and return []).
                try:
                    page.wait_for_selector(CARD_WAIT_SELECTOR, timeout=self.page_timeout_ms)
                except Exception:
                    logger.warning(
                        "job=%s card selector not found on %s — returning page HTML anyway",
                        job_id, url,
                    )
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

    # ------------------------------------------------------------------
    # Phone number fallback
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Overlay removal
    # ------------------------------------------------------------------

    def _remove_overlays(self, page) -> None:
        js = """
        try {
            var ids = ['loginPop', 'login_modal', 'modal_close', 'jd_modal', 'jdLgnbox'];
            ids.forEach(function(id){ var el = document.getElementById(id); if(el) el.remove(); });
            var classes = ['loginPop', 'new__login_pop', 'jd_modal', 'login_overlay', 'modal-backdrop', 'jdLgnbox'];
            classes.forEach(function(cls){ document.querySelectorAll('[class*="'+cls+'"]').forEach(function(el){ el.remove(); }); });
            document.body.style.overflow = ''; document.body.style.position = '';
        } catch (e) {}
        """
        try:
            page.evaluate(js)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Homepage form interaction (headed mode only)
    # ------------------------------------------------------------------

    def _search_on_homepage(self, page, skill: str, pincode: str) -> tuple[str | None, str, str]:
        """Perform a human-like search on JustDial homepage and capture the best JSON/HTML result.

        Returns (content, status, actual_search_url)
        status: 'ok' | 'captcha' | 'error' | 'empty'
        """
        HOME = "https://www.justdial.com/"
        try:
            page.goto(HOME, wait_until="load", timeout=180000)
            page.wait_for_timeout(2000)
        except Exception as exc:
            logger.warning("Homepage load failed (%s), falling back to direct search URL", exc)
            try:
                direct_url = build_search_url(pincode, skill, 1)
                page.goto(direct_url, wait_until="domcontentloaded", timeout=max(self.page_timeout_ms, 60000))
                page.wait_for_timeout(2000)
            except Exception as exc2:
                logger.warning("Direct search URL also failed: %s", exc2)
                return None, "error", ""

        self._remove_overlays(page)

        responses = []
        def _on_response(resp):
            try:
                responses.append((resp.url, resp))
            except Exception:
                pass

        page.on("response", _on_response)

        what_selectors = [
            "input[placeholder*='Search']",
            "input[id='search_what']",
            "input[name='search_what']",
            "#what",
            ".search_main input[type='text']",
        ]
        what = None
        for sel in what_selectors:
            locator = page.locator(sel)
            if locator.count() > 0:
                what = locator.first
                break

        if not what:
            logger.error("Cannot find 'What' search box on homepage")
            try:
                page.off("response", _on_response)
            except Exception:
                pass
            try:
                with open("debug_no_what_box_page.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
            except Exception:
                pass
            return self._load_direct_search_from_homepage_fallback(page, skill, pincode)

        try:
            what.click()
        except Exception:
            try:
                page.evaluate("el => el.click()", what)
            except Exception:
                pass
        page.wait_for_timeout(300)
        for ch in skill:
            what.type(ch, delay=random.randint(50, 140))

        where_selectors = [
            "input[placeholder*='Location']",
            "input[id='search_where']",
            "input[name='search_where']",
            "#where",
        ]
        where = None
        for sel in where_selectors:
            locator = page.locator(sel)
            if locator.count() > 0:
                where = locator.first
                break

        if where:
            try:
                where.click()
            except Exception:
                try:
                    page.evaluate("el => el.click()", where)
                except Exception:
                    pass
            page.wait_for_timeout(300)
            try:
                where.fill("")
            except Exception:
                pass
            for ch in pincode:
                where.type(ch, delay=random.randint(80, 160))

            try:
                page.wait_for_timeout(800)
                suggestions = page.locator(".react-autosuggest__suggestion")
                if suggestions.count() > 0:
                    selected = False
                    for i in range(min(suggestions.count(), 16)):
                        text = suggestions.nth(i).inner_text()
                        if pincode in (text or "") and "detect" not in (text or "").lower():
                            suggestions.nth(i).click()
                            selected = True
                            break
                    if not selected:
                        suggestions.nth(0).click()
                else:
                    where.press("Tab")
            except Exception:
                try:
                    where.press("Tab")
                except Exception:
                    pass

        submit_selectors = [".search_button", ".search_btnbox", "#search_btn", "button[type='submit']"]
        submitted = False
        for sel in submit_selectors:
            try:
                btn = page.locator(sel)
                if btn.count() > 0:
                    btn.first.click()
                    submitted = True
                    break
            except Exception:
                continue
        if not submitted:
            try:
                what.press("Enter")
            except Exception:
                pass

        page.wait_for_timeout(3000)
        actual_url = page.url

        content = page.content()
        if self._detect_captcha(content):
            try:
                page.off("response", _on_response)
            except Exception:
                pass
            return None, "captcha", actual_url

        self._scroll_page(page)
        page.wait_for_timeout(2000)

        try:
            page.off("response", _on_response)
        except Exception:
            pass

        best_body = None
        best_count = 0
        for url, resp in responses:
            try:
                ctype = resp.headers.get("content-type", "")
                if "json" not in ctype.lower():
                    continue
                if "justdial" not in url.lower() and "jdmagicbox" not in url.lower():
                    continue
                text = resp.text()
                if not text or len(text) < 50:
                    continue
                parsed = json.loads(text)
                api_data = parsed.get("results", {}).get("data", [])
                if isinstance(api_data, list) and len(api_data) > best_count:
                    best_count = len(api_data)
                    best_body = text
                    logger.info("Captured XHR response with %d listings from %s", best_count, url)
            except Exception as e:
                logger.debug("Failed to parse XHR response from %s: %s", url, e)
                continue

        if best_body and best_count > 0:
            return best_body, "ok", actual_url

        try:
            nd_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', content, re.DOTALL)
            if nd_match:
                nd = json.loads(nd_match.group(1))
                nd_data = nd.get("props", {}).get("pageProps", {}).get("results", {}).get("data", [])
                if isinstance(nd_data, list) and nd_data:
                    cols = ["id", "name", "addr", "rating", "reviews", "vn", "tag"]
                    rows = []
                    for item in nd_data:
                        rows.append([
                            item.get("id", ""),
                            item.get("company_name", item.get("name", "")),
                            item.get("address", item.get("addr", "")),
                            str(item.get("rating", item.get("ratingstar", ""))),
                            str(item.get("ratingcount", "")),
                            item.get("mobile", item.get("vn", item.get("phone", ""))),
                            item.get("tag", ""),
                        ])
                    return json.dumps({"results": {"columns": cols, "data": rows}}), "ok", actual_url
        except Exception:
            pass

        return content, "ok", actual_url

    def _load_direct_search_from_homepage_fallback(
        self,
        page,
        skill: str,
        pincode: str,
    ) -> tuple[str | None, str, str]:
        """Use the direct results URL when the homepage form is unavailable."""
        direct_url = build_search_url(pincode, skill, 1)
        try:
            html = self._load_page_with_retry(page, direct_url, None)
            return html, "ok", direct_url
        except PageLoadError as exc:
            logger.warning("Direct search fallback failed: %s", exc)
            return None, "error", direct_url
