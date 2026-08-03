from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..types import Job, empty_job
from ._pagination import with_query_param
from .base import Scraper

_JOB_ID_RE = re.compile(r"/jobs/view/[^/]*?-?(\d{6,})(?:/|\?|$)")

# LinkedIn's guest jobs API returns a fixed batch of cards per request; deeper
# pages are requested by advancing the `start` offset.
_LINKEDIN_PAGE_SIZE = 25


def _extract_job_id(url: str | None) -> str | None:
    if not url:
        return None
    match = _JOB_ID_RE.search(url)
    return match.group(1) if match else None


class LinkedinScraper(Scraper):
    name = "linkedin"

    def page_url(self, page: int) -> str | None:
        if page == 0:
            return self.url
        return with_query_param(self.url, "start", str(page * _LINKEDIN_PAGE_SIZE))

    def parse_detail(self, html: str) -> str | None:
        soup = BeautifulSoup(html, "lxml")
        for selector in (
            ".show-more-less-html__markup",
            ".description__text",
            ".jobs-box__html-content",
        ):
            el = soup.select_one(selector)
            if el:
                text = el.get_text("\n", strip=True)
                if text:
                    return text
        return None

    def parse(self, html: str) -> list[Job]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("li") or soup.select("div.base-search-card")
        results: list[Job] = []
        for card in cards:
            title_el = card.select_one("h3.base-search-card__title") or card.select_one(
                ".base-search-card__title"
            )
            company_el = card.select_one("h4.base-search-card__subtitle a") or card.select_one(
                ".base-search-card__subtitle"
            )
            loc_el = card.select_one(".job-search-card__location")
            link_el = card.select_one("a.base-card__full-link") or card.select_one(
                "a[href*='/jobs/view/']"
            )
            posted_el = card.select_one("time.job-search-card__listdate") or card.select_one(
                "time.job-search-card__listdate--new"
            )

            title = title_el.get_text(" ", strip=True) if title_el else None
            company = company_el.get_text(" ", strip=True) if company_el else None
            location = loc_el.get_text(" ", strip=True) if loc_el else None
            href_value = link_el.get("href") if link_el else None
            href = str(href_value) if href_value else None
            url = href.split("?", 1)[0] if href else None

            posted_date: str | None = None
            if posted_el is not None:
                datetime_attr = posted_el.get("datetime")
                if isinstance(datetime_attr, str) and datetime_attr:
                    posted_date = datetime_attr
                else:
                    posted_date = posted_el.get_text(" ", strip=True) or None

            if title and company:
                job = empty_job(self.name, title, company)
                job["location"] = location
                job["url"] = url
                job["posted_date"] = posted_date
                job["job_id"] = _extract_job_id(url)
                results.append(job)
        return results
