from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..types import Job

if TYPE_CHECKING:
    from ..fetchers import FetchChain, FetchResult


class Scraper(ABC):
    name: str
    requires_search_html: bool = True
    # True for sites we hit via a JSON API (one pooled request) rather than by
    # paginating HTML pages. Governs which default page budget applies — see
    # AppConfig.max_pages_for / config.yaml (`max_pages` vs `api_max_pages`).
    api_backed: bool = False

    def __init__(self, url: str, limit: int, max_pages: int = 1) -> None:
        self.url = url
        self.limit = limit
        self.max_pages = max_pages

    @abstractmethod
    def parse(self, html: str) -> list[Job]: ...

    def collect(self, html: str) -> list[Job]:
        """Produce the job list for a fetched page. Default: parse the HTML.

        Sites backed by a JSON API override this to try the API first and fall
        back to ``parse()`` on failure. The runner calls ``collect()``; keeping
        the API attempt out of ``parse()`` lets the HTML parsers stay pure and
        network-free (and unit-testable in isolation)."""
        return self.parse(html)

    def page_url(self, page: int) -> str | None:
        """URL to fetch for a 0-indexed page.

        Base implementation knows only page 0 (the configured search URL) and
        reports no further pages. Sites that support pagination override this to
        return deeper-page URLs; the runner stops once it returns None."""
        return self.url if page == 0 else None

    def parse_detail(self, html: str) -> str | None:
        return None

    def detail_fetch(self, url: str, fetcher: FetchChain) -> FetchResult:
        return fetcher.fetch(url)
