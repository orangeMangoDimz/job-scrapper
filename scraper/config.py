from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, ConfigDict


def redact_proxy_url(proxy_url: str) -> str:
    """Hide a proxy password in logged/returned strings (keeps the username).

    Shared by the scraper runner, fetchers, and the MCP server so a proxy URL
    whose userinfo carries a password never reaches logs — and, via loguru
    breadcrumbs, Sentry. Returns a safe placeholder on any parse failure.
    """
    try:
        p = urlparse(proxy_url)
        if not p.hostname:
            return proxy_url
        host = p.hostname
        port = f":{p.port}" if p.port else ""
        if p.username is not None and p.username != "":
            netloc = f"{p.username}:***@{host}{port}"
        elif p.password is not None:
            netloc = f"***@{host}{port}"
        else:
            netloc = f"{host}{port}"
        return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))
    except Exception:
        return "<unparseable proxy url>"


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

ACCEPT_LANGUAGE = "id-ID,id;q=0.9,en;q=0.8"

# curl_cffi browser-impersonation profile (shared by every curl_cffi caller)
CHROME_IMPERSONATE = "chrome131"

# Playwright browser-context identity
BROWSER_LOCALE = "id-ID"
BROWSER_VIEWPORT: dict[str, int] = {"width": 1366, "height": 768}

CHALLENGE_MARKERS: tuple[str, ...] = (
    "Just a moment",
    "challenge-platform",
    "cf-browser-verification",
    "Attention Required",
)


class FetchTuning(BaseModel):
    """Network tuning knobs, sourced from config.yaml `timeouts:`."""

    model_config = ConfigDict(frozen=True)

    http_seconds: int = 30  # curl_cffi + cloudscraper GET timeout
    playwright_goto_ms: int = 60_000  # page.goto timeout
    playwright_networkidle_ms: int = 15_000  # wait_for_load_state("networkidle")
    playwright_settle_seconds: int = 2  # post-nav sleep before page.content()
    indeed_api_seconds: int = 30  # indeed GraphQL POST timeout
