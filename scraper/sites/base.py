from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..config import FetchTuning
from ..types import Job

if TYPE_CHECKING:
    from ..fetchers import FetchChain, FetchResult


class Scraper(ABC):
    name: str
    requires_search_html: bool = True

    def __init__(self, url: str, limit: int, tuning: FetchTuning | None = None) -> None:
        self.url = url
        self.limit = limit
        self.tuning = tuning or FetchTuning()

    @abstractmethod
    def parse(self, html: str) -> list[Job]: ...

    def parse_detail(self, html: str) -> str | None:
        return None

    def detail_fetch(self, url: str, fetcher: FetchChain) -> FetchResult:
        return fetcher.fetch(url)
