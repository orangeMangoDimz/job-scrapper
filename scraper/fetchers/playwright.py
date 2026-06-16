# scraper/fetchers/playwright.py
from __future__ import annotations

import contextlib
import time

from ..config import BROWSER_LOCALE, BROWSER_VIEWPORT, USER_AGENT, FetchTuning, redact_proxy_url
from ..log import get_logger
from .base import FetchAttempt, detect_challenge

_LOG = get_logger()


class PlaywrightFetcher:
    name = "playwright"

    def __init__(self, proxy: str | None = None, tuning: FetchTuning | None = None) -> None:
        self._proxy = proxy
        self._tuning = tuning or FetchTuning()

    def fetch(self, url: str) -> tuple[str | None, FetchAttempt]:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-untyped]
        except Exception as exc:
            _LOG.warning("[playwright] not installed: {}", exc)
            return None, FetchAttempt(
                fetcher=self.name,
                code="not_installed",
                detail=f"{type(exc).__name__}: {exc}",
            )

        stealth_v2 = None
        stealth_sync = None
        try:
            from playwright_stealth import Stealth as stealth_v2  # type: ignore
        except Exception:
            try:
                from playwright_stealth import stealth_sync  # type: ignore
            except Exception:
                stealth_sync = None

        if self._proxy:
            _LOG.info("[playwright] using proxy: {}", redact_proxy_url(self._proxy))

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-gpu",
                    ],
                )
                try:
                    context_kwargs: dict = {
                        "user_agent": USER_AGENT,
                        "locale": BROWSER_LOCALE,
                        "viewport": dict(BROWSER_VIEWPORT),
                    }
                    if self._proxy:
                        context_kwargs["proxy"] = {"server": self._proxy}
                    context = browser.new_context(**context_kwargs)
                    page = context.new_page()
                    if stealth_v2 is not None:
                        stealth_v2().apply_stealth_sync(page)
                    elif stealth_sync is not None:
                        stealth_sync(page)

                    page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self._tuning.playwright_goto_ms,
                    )
                    with contextlib.suppress(Exception):
                        page.wait_for_load_state(
                            "networkidle", timeout=self._tuning.playwright_networkidle_ms
                        )
                    time.sleep(self._tuning.playwright_settle_seconds)
                    html = page.content()
                finally:
                    with contextlib.suppress(Exception):
                        browser.close()
        except Exception as exc:
            msg = str(exc)
            lowered = msg.lower()
            if "asyncio" in lowered and "loop" in lowered:
                _LOG.error("[playwright] asyncio conflict on {}", url)
                return None, FetchAttempt(
                    fetcher=self.name,
                    code="runtime_error",
                    detail="asyncio sync-API conflict",
                )
            if "timeout" in lowered:
                _LOG.warning("[playwright] timeout on {}", url)
                return None, FetchAttempt(
                    fetcher=self.name,
                    code="timeout",
                    detail=msg[:200],
                )
            _LOG.error("[playwright] error on {}: {}", url, exc)
            return None, FetchAttempt(
                fetcher=self.name,
                code="runtime_error",
                detail=f"{type(exc).__name__}: {msg[:200]}",
            )

        challenge = detect_challenge(html)
        if challenge:
            _LOG.warning("[playwright] {} blocked by challenge page", url)
            return None, FetchAttempt(
                fetcher=self.name,
                code="challenge",
                detail=challenge,
            )
        return html, FetchAttempt(fetcher=self.name, code="ok")
