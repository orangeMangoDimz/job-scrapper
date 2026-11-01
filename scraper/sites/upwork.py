from __future__ import annotations

from ..types import Job
from .base import Scraper


class UpworkScraper(Scraper):
    """Registers Upwork with the runner. All data comes from scraper/api/upwork.py."""

    name = "upwork"
    requires_search_html = False
    api_only = True

    def parse(self, html: str) -> list[Job]:
        return []
