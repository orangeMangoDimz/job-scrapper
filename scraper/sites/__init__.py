from __future__ import annotations

from .base import Scraper
from .glints import GlintsScraper
from .indeed import IndeedScraper
from .jobstreet import JobstreetScraper
from .linkedin import LinkedinScraper
from .upwork import UpworkScraper

SCRAPERS: dict[str, type[Scraper]] = {
    cls.name: cls
    for cls in (JobstreetScraper, GlintsScraper, LinkedinScraper, IndeedScraper, UpworkScraper)
}

__all__ = [
    "Scraper",
    "SCRAPERS",
    "JobstreetScraper",
    "GlintsScraper",
    "LinkedinScraper",
    "IndeedScraper",
    "UpworkScraper",
]
