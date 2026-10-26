from __future__ import annotations

from ..sites.linkedin import LinkedinScraper
from ..types import Job
from .client import ApiClient
from .window import seconds_window

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
PAGE_SIZE = 10  # fixed by LinkedIn's guest endpoint
MAX_PAGES = 5


class LinkedinApi:
    """LinkedIn's guest endpoint returns HTML cards; parsing reuses LinkedinScraper."""

    name = "linkedin"
    country_location: str | None = "Indonesia"

    def __init__(self, client: ApiClient) -> None:
        self._client = client
        self._parser = LinkedinScraper(url=SEARCH_URL, limit=PAGE_SIZE)

    def search(
        self, keyword: str, location: str | None, max_age_hours: int | None, limit: int
    ) -> list[Job]:
        jobs: list[Job] = []
        for page in range(MAX_PAGES):
            params = {"keywords": keyword, "location": location or "Indonesia"}
            seconds = seconds_window(max_age_hours)
            if seconds is not None:
                params["f_TPR"] = f"r{seconds}"
            params["start"] = str(page * PAGE_SIZE)
            cards = self._parser.parse(self._client.get_text(SEARCH_URL, params=params))
            if not cards:
                break
            jobs.extend(cards)
            # a short page is the last one; skip the extra call (LinkedIn rate-limits fast)
            if len(cards) < PAGE_SIZE or len(jobs) >= limit:
                break
        return jobs[:limit]

    def detail(self, job: Job) -> str | None:
        return None  # no detail API; the runner fetches the job page
