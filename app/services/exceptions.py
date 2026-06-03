"""Custom exceptions for scraper operations."""


class ScraperError(Exception):
    """Base scraper error."""


class CaptchaError(ScraperError):
    """Raised when a CAPTCHA screen is detected."""


class PageLoadError(ScraperError):
    """Raised when a page fails to load after retries."""
