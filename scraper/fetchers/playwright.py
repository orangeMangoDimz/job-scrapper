# scraper/fetchers/playwright.py
from __future__ import annotations

import contextlib
import time

from ..config import USER_AGENT
from ..log import get_logger, redact_proxy_url
from .base import FetchAttempt, detect_challenge

_LOG = get_logger()


class PlaywrightFetcher:
    name = "playwright"

    def __init__(self, proxy: str | None = None) -> None:
        self._proxy = proxy

    def fetch(self, url: str) -> tuple[str | None, FetchAttempt]:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-untyped]
        except Exception as exc:
            _LOG.warning("[playwright] not installed: %s", exc)
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
            _LOG.info("[playwright] using proxy: %s", redact_proxy_url(self._proxy))

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
                context_kwargs: dict = {
                    "user_agent": USER_AGENT,
                    "locale": "id-ID",
                    "viewport": {"width": 1366, "height": 768},
                }
                if self._proxy:
                    context_kwargs["proxy"] = {"server": self._proxy}
                context = browser.new_context(**context_kwargs)
                page = context.new_page()
                if stealth_v2 is not None:
                    stealth_v2().apply_stealth_sync(page)
                elif stealth_sync is not None:
                    stealth_sync(page)

                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                with contextlib.suppress(Exception):
                    page.wait_for_load_state("networkidle", timeout=15_000)
                time.sleep(2)
                html = page.content()
                context.close()
                browser.close()
        except Exception as exc:
            msg = str(exc)
            lowered = msg.lower()
            if "asyncio" in lowered and "loop" in lowered:
                _LOG.error("[playwright] asyncio conflict on %s", url)
                return None, FetchAttempt(
                    fetcher=self.name,
                    code="runtime_error",
                    detail="asyncio sync-API conflict",
                )
            if "timeout" in lowered:
                _LOG.warning("[playwright] timeout on %s", url)
                return None, FetchAttempt(
                    fetcher=self.name,
                    code="timeout",
                    detail=msg[:200],
                )
            _LOG.error("[playwright] error on %s: %s", url, exc)
            return None, FetchAttempt(
                fetcher=self.name,
                code="runtime_error",
                detail=f"{type(exc).__name__}: {msg[:200]}",
            )

        challenge = detect_challenge(html)
        if challenge:
            _LOG.warning("[playwright] %s blocked by challenge page", url)
            return None, FetchAttempt(
                fetcher=self.name,
                code="challenge",
                detail=challenge,
            )
        return html, FetchAttempt(fetcher=self.name, code="ok")
