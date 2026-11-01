# scraper/fetchers/cloudscraper.py
from __future__ import annotations

import cloudscraper

from ..config import ACCEPT_LANGUAGE, USER_AGENT
from ..log import get_logger, redact_proxy_url
from .base import FetchAttempt, detect_challenge

_LOG = get_logger()


class CloudscraperFetcher:
    name = "cloudscraper"

    def __init__(self, proxy: str | None = None) -> None:
        self._proxy = proxy

    def fetch(self, url: str) -> tuple[str | None, FetchAttempt]:
        if self._proxy:
            _LOG.info("[cloudscraper] using proxy: %s", redact_proxy_url(self._proxy))

        try:
            scraper = cloudscraper.create_scraper(  # type: ignore[attr-defined]
                browser={"browser": "chrome", "platform": "linux", "mobile": False}
            )
            scraper.headers.update({"User-Agent": USER_AGENT, "Accept-Language": ACCEPT_LANGUAGE})
            proxies = {"http": self._proxy, "https": self._proxy} if self._proxy else None
            response = scraper.get(url, timeout=30, proxies=proxies)
        except Exception as exc:
            _LOG.error("[cloudscraper] error on %s: %s", url, exc)
            return None, FetchAttempt(
                fetcher=self.name,
                code="runtime_error",
                detail=f"{type(exc).__name__}: {exc}",
            )

        status = response.status_code
        if status != 200:
            _LOG.warning("[cloudscraper] %s status=%d", url, status)
            return None, FetchAttempt(
                fetcher=self.name,
                code=f"http_{status}",
                detail=f"status={status}",
            )

        text = response.text
        challenge = detect_challenge(text)
        if challenge:
            _LOG.warning("[cloudscraper] %s blocked by challenge page", url)
            return None, FetchAttempt(
                fetcher=self.name,
                code="challenge",
                detail=challenge,
            )
        return text, FetchAttempt(fetcher=self.name, code="ok")
