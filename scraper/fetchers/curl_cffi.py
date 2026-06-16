# scraper/fetchers/curl_cffi.py
from __future__ import annotations

from ..config import ACCEPT_LANGUAGE, CHROME_IMPERSONATE, USER_AGENT, FetchTuning, redact_proxy_url
from ..log import get_logger
from .base import FetchAttempt, detect_challenge

_LOG = get_logger()


class CurlCffiFetcher:
    name = "curl_cffi"

    def __init__(self, proxy: str | None = None, tuning: FetchTuning | None = None) -> None:
        self._proxy = proxy
        self._tuning = tuning or FetchTuning()

    def fetch(self, url: str) -> tuple[str | None, FetchAttempt]:
        try:
            from curl_cffi import requests as cffi_requests  # type: ignore[attr-defined]
        except Exception as exc:
            _LOG.warning("[curl_cffi] not installed: {}", exc)
            return None, FetchAttempt(
                fetcher=self.name,
                code="not_installed",
                detail=f"{type(exc).__name__}: {exc}",
            )

        if self._proxy:
            _LOG.info("[curl_cffi] using proxy: {}", redact_proxy_url(self._proxy))

        try:
            proxies = {"http": self._proxy, "https": self._proxy} if self._proxy else None
            response = cffi_requests.get(
                url,
                impersonate=CHROME_IMPERSONATE,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": ACCEPT_LANGUAGE,
                },
                timeout=self._tuning.http_seconds,
                proxies=proxies,
            )
        except Exception as exc:
            _LOG.error("[curl_cffi] error on {}: {}", url, exc)
            return None, FetchAttempt(
                fetcher=self.name,
                code="runtime_error",
                detail=f"{type(exc).__name__}: {exc}",
            )

        status = response.status_code
        if status != 200:
            _LOG.warning("[curl_cffi] {} status={}", url, status)
            return None, FetchAttempt(
                fetcher=self.name,
                code=f"http_{status}",
                detail=f"status={status}",
            )

        text = response.text
        challenge = detect_challenge(text)
        if challenge:
            _LOG.warning("[curl_cffi] {} blocked by challenge page", url)
            return None, FetchAttempt(
                fetcher=self.name,
                code="challenge",
                detail=challenge,
            )
        return text, FetchAttempt(fetcher=self.name, code="ok")
