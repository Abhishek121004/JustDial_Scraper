"""Rotating proxy manager for Playwright browser sessions.

Supports a list of proxy URLs that are rotated per-job or per-page.
Failed/blocked proxies are automatically blacklisted for the current session.

Proxy URL format:
    http://user:pass@host:port
    http://host:port
    socks5://user:pass@host:port
"""

import logging
import random
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProxyEntry:
    url: str
    failures: int = 0
    successes: int = 0
    blacklisted: bool = False


class ProxyManager:
    """Thread-safe rotating proxy manager.

    Usage:
        manager = ProxyManager(["http://p1:8080", "http://p2:8080"])
        proxy = manager.get_proxy()           # returns next proxy dict or None
        manager.report_success(proxy_url)
        manager.report_failure(proxy_url)     # auto-blacklists after max_failures
    """

    def __init__(
        self,
        proxy_urls: list[str],
        max_failures: int = 3,
        shuffle: bool = True,
    ):
        self._lock = threading.Lock()
        self._max_failures = max_failures
        entries = [ProxyEntry(url=u.strip()) for u in proxy_urls if u.strip()]
        if shuffle:
            random.shuffle(entries)
        self._proxies: list[ProxyEntry] = entries
        self._index: int = 0
        logger.info("ProxyManager initialised with %d proxies", len(self._proxies))

    @classmethod
    def from_config(cls, proxy_list_str: str | None, single_proxy: str | None = None) -> "ProxyManager | None":
        """Build a ProxyManager from config values.

        proxy_list_str: newline/comma-separated proxy URLs (from PROXY_LIST env var)
        single_proxy:   single proxy URL (legacy PROXY_URL env var)
        Returns None if no proxies are configured.
        """
        urls: list[str] = []
        if proxy_list_str:
            # Support both newline-separated and comma-separated lists
            for part in proxy_list_str.replace("\n", ",").split(","):
                part = part.strip()
                if part:
                    urls.append(part)
        if single_proxy and single_proxy.strip() and single_proxy.strip() not in urls:
            urls.append(single_proxy.strip())
        if not urls:
            return None
        return cls(urls)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def has_proxies(self) -> bool:
        with self._lock:
            return any(not p.blacklisted for p in self._proxies)

    def get_proxy(self) -> dict | None:
        """Return the next available proxy as a Playwright proxy dict, or None."""
        with self._lock:
            available = [p for p in self._proxies if not p.blacklisted]
            if not available:
                logger.warning("No proxies available — all blacklisted or list empty")
                return None
            # Round-robin with wraparound
            entry = available[self._index % len(available)]
            self._index = (self._index + 1) % len(available)
            return self._build_playwright_proxy(entry.url)

    def get_random_proxy(self) -> dict | None:
        """Return a random available proxy as a Playwright proxy dict, or None."""
        with self._lock:
            available = [p for p in self._proxies if not p.blacklisted]
            if not available:
                return None
            entry = random.choice(available)
            return self._build_playwright_proxy(entry.url)

    def report_success(self, proxy_url: str) -> None:
        """Mark a proxy as having succeeded."""
        with self._lock:
            for entry in self._proxies:
                if entry.url == proxy_url:
                    entry.successes += 1
                    entry.failures = max(0, entry.failures - 1)  # partial forgiveness
                    return

    def report_failure(self, proxy_url: str) -> None:
        """Mark a proxy as having failed. Blacklists after max_failures."""
        with self._lock:
            for entry in self._proxies:
                if entry.url == proxy_url:
                    entry.failures += 1
                    if entry.failures >= self._max_failures:
                        entry.blacklisted = True
                        logger.warning(
                            "Proxy blacklisted after %d failures: %s",
                            entry.failures,
                            self._redact(entry.url),
                        )
                    else:
                        logger.info(
                            "Proxy failure %d/%d: %s",
                            entry.failures,
                            self._max_failures,
                            self._redact(entry.url),
                        )
                    return

    def stats(self) -> list[dict]:
        """Return a summary of all proxy statuses (passwords redacted)."""
        with self._lock:
            return [
                {
                    "url": self._redact(p.url),
                    "successes": p.successes,
                    "failures": p.failures,
                    "blacklisted": p.blacklisted,
                }
                for p in self._proxies
            ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_playwright_proxy(url: str) -> dict:
        """Convert a proxy URL to a Playwright proxy dict.

        Supports:
            http://host:port
            http://user:pass@host:port
            socks5://user:pass@host:port
        """
        from urllib.parse import urlparse
        parsed = urlparse(url)
        proxy: dict = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
        if parsed.username:
            proxy["username"] = parsed.username
        if parsed.password:
            proxy["password"] = parsed.password
        return proxy

    @staticmethod
    def _redact(url: str) -> str:
        """Redact password from proxy URL for safe logging."""
        from urllib.parse import urlparse, urlunparse
        try:
            p = urlparse(url)
            if p.password:
                netloc = f"{p.username}:***@{p.hostname}:{p.port}"
                return urlunparse(p._replace(netloc=netloc))
        except Exception:
            pass
        return url
