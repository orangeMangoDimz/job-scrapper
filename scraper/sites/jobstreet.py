from __future__ import annotations

from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup

from ..types import Job, empty_job
from ._api import request_json
from ._next_data import extract_next_data, walk_dicts
from .base import Scraper

# JobStreet/SEEK's public v5 JobSearch REST API (no auth). The older chalice-search
# v4 endpoint was deprecated (404); v5 is the current replacement that powers the
# search page. Reverse-engineered — may change; we fall back to HTML on any failure.
_API_URL = "https://id.jobstreet.com/api/jobsearch/v5/search"
_SITE_KEY = "ID-Main"  # Indonesia
_API_HEADERS = {
    "accept": "application/json",
    "referer": "https://id.jobstreet.com/",
}


def _keyword_from_url(url: str) -> str:
    """Recover the search keyword from the HTML search URL path, e.g.
    https://id.jobstreet.com/id/software-engineer-jobs?... -> "software engineer"."""
    seg = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    if seg.endswith("-jobs"):
        seg = seg[: -len("-jobs")]
    return seg.replace("-", " ").strip()


def _job_from_api(item: object) -> Job | None:
    """Map one v5 search result to the canonical Job shape."""
    if not isinstance(item, dict):
        return None
    title = item.get("title")
    advertiser = item.get("advertiser")
    company = advertiser.get("description") if isinstance(advertiser, dict) else None
    company = company or item.get("companyName")
    if not title or not company:
        return None

    job = empty_job("jobstreet", str(title).strip(), str(company).strip())
    job_id = item.get("id")
    job["job_id"] = str(job_id) if job_id else None
    job["url"] = f"https://id.jobstreet.com/id/job/{job_id}" if job_id else None

    locations = item.get("locations")
    if isinstance(locations, list) and locations and isinstance(locations[0], dict):
        label = locations[0].get("label")
        job["location"] = str(label).strip() if label else None

    salary = item.get("salaryLabel")
    job["salary"] = salary if isinstance(salary, str) and salary.strip() else None

    listing_date = item.get("listingDate")
    job["posted_date"] = listing_date if isinstance(listing_date, str) else None

    work_types = item.get("workTypes")
    if isinstance(work_types, list) and work_types and isinstance(work_types[0], str):
        job["employment_type"] = work_types[0].lower()

    arrangements = item.get("workArrangements")
    if isinstance(arrangements, dict):
        data = arrangements.get("data")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            label = data[0].get("label")
            if isinstance(label, dict) and isinstance(label.get("text"), str):
                job["work_type"] = label["text"].lower()

    return job


def _company_from_candidate(candidate: dict) -> str | None:
    if "companyName" in candidate:
        return candidate["companyName"]
    advertiser = candidate.get("advertiser")
    if isinstance(advertiser, dict) and advertiser.get("description"):
        return advertiser["description"]
    company = candidate.get("company")
    if isinstance(company, str):
        return company
    if isinstance(company, dict):
        return company.get("name")
    return None


def _location_from_candidate(candidate: dict) -> str | None:
    location = candidate.get("locationLabel") or candidate.get("location")
    if isinstance(location, dict):
        return location.get("label") or location.get("name")
    if isinstance(location, list) and location:
        first = location[0]
        if isinstance(first, dict):
            return first.get("label")
        return str(first)
    if isinstance(location, str):
        return location
    return None


def _salary_from_candidate(candidate: dict) -> str | None:
    if isinstance(candidate.get("salaryLabel"), str):
        return candidate["salaryLabel"]
    salary = candidate.get("salary")
    if isinstance(salary, dict):
        for key in ("label", "displayText", "text"):
            if isinstance(salary.get(key), str):
                return salary[key]
    if isinstance(candidate.get("salaryRange"), str):
        return candidate["salaryRange"]
    return None


def _posted_date_from_candidate(candidate: dict) -> str | None:
    for key in ("listingDate", "createdDate", "createdAt", "postedDate"):
        value = candidate.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _work_type_from_candidate(candidate: dict) -> str | None:
    arrangements = candidate.get("workArrangements")
    if isinstance(arrangements, list) and arrangements:
        first = arrangements[0]
        if isinstance(first, dict):
            label = first.get("label") or first.get("name")
            if isinstance(label, str):
                return label.lower()
        if isinstance(first, str):
            return first.lower()
    return None


def _employment_type_from_candidate(candidate: dict) -> str | None:
    work_types = candidate.get("workTypes")
    if isinstance(work_types, list) and work_types:
        first = work_types[0]
        if isinstance(first, dict):
            label = first.get("label") or first.get("name")
            if isinstance(label, str):
                return label.lower()
        if isinstance(first, str):
            return first.lower()
    employment = candidate.get("employmentType")
    if isinstance(employment, str):
        return employment.lower()
    return None


class JobstreetScraper(Scraper):
    name = "jobstreet"
    # The runner still fetches the search HTML (used as the fallback below), but a
    # blocked/empty fetch must NOT bail before we've tried the API — so opt out of
    # the "require HTML" gate like Indeed does.
    requires_search_html = False
    api_backed = True

    def collect(self, html: str) -> list[Job]:
        api_jobs = self._fetch_api_jobs()
        if api_jobs:
            return api_jobs
        # API failed/empty (or WAF-blocked) — fall back to the fetched search page.
        return self.parse(html)

    def _fetch_api_jobs(self) -> list[Job]:
        keyword = _keyword_from_url(self.url)
        if not keyword:
            return []
        # One call for a pool sized to the pagination budget; the runner dedups it
        # down to `limit` brand-new jobs (same single-pool approach as Indeed).
        page_size = max(1, min(self.limit * self.max_pages, 100))
        api_url = (
            f"{_API_URL}?siteKey={_SITE_KEY}"
            f"&keywords={quote(keyword)}&pageSize={page_size}&page=1"
        )
        payload = request_json("GET", api_url, headers=_API_HEADERS, label="jobstreet-api")
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        if not isinstance(data, list):
            return []
        results: list[Job] = []
        for item in data:
            job = _job_from_api(item)
            if job is not None:
                results.append(job)
        return results

    def parse_detail(self, html: str) -> str | None:
        data = extract_next_data(html)
        if data:
            candidates: list[dict] = []
            walk_dicts(
                data,
                lambda d: any(k in d for k in ("requirements", "jobDescription", "description")),
                candidates,
            )
            for candidate in candidates:
                for key in ("requirements", "jobDescription", "description"):
                    value = candidate.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        soup = BeautifulSoup(html, "lxml")
        for selector in (
            "[data-automation='jobAdDetails']",
            "[data-automation='jobDescription']",
            ".job-description",
        ):
            el = soup.select_one(selector)
            if el:
                text = el.get_text("\n", strip=True)
                if text:
                    return text
        return None

    def parse(self, html: str) -> list[Job]:
        results = self._parse_next_data(html)
        if results:
            return results
        return self._parse_html(html)

    def _parse_next_data(self, html: str) -> list[Job]:
        data = extract_next_data(html)
        if not data:
            return []
        candidates: list[dict] = []
        walk_dicts(
            data,
            lambda d: ("jobTitle" in d or "title" in d)
            and ("companyName" in d or "advertiser" in d or "company" in d),
            candidates,
        )
        results: list[Job] = []
        seen: set[tuple[str, str]] = set()
        for candidate in candidates:
            title = candidate.get("jobTitle") or candidate.get("title")
            company = _company_from_candidate(candidate)
            if not title or not company:
                continue
            key = (str(title), str(company))
            if key in seen:
                continue
            seen.add(key)

            job = empty_job(self.name, str(title).strip(), str(company).strip())
            location = _location_from_candidate(candidate)
            job["location"] = str(location).strip() if location else None
            job_id = candidate.get("id")
            job["job_id"] = str(job_id) if job_id else None
            job["url"] = f"https://id.jobstreet.com/id/job/{job_id}" if job_id else None
            job["salary"] = _salary_from_candidate(candidate)
            job["posted_date"] = _posted_date_from_candidate(candidate)
            job["work_type"] = _work_type_from_candidate(candidate)
            job["employment_type"] = _employment_type_from_candidate(candidate)

            results.append(job)
        return results

    def _parse_html(self, html: str) -> list[Job]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select(
            "article[data-card-type='JobCard'], article[data-automation='normalJob']"
        )
        results: list[Job] = []
        for card in cards:
            title_el = card.select_one("[data-automation='jobTitle']") or card.select_one("a")
            company_el = card.select_one("[data-automation='jobCompany']")
            loc_el = card.select_one("[data-automation='jobLocation']")
            salary_el = card.select_one("[data-automation='jobSalary']")
            posted_el = card.select_one("[data-automation='jobListingDate']")
            work_type_el = card.select_one("[data-automation='workArrangement']")

            title = title_el.get_text(strip=True) if title_el else None
            company = company_el.get_text(strip=True) if company_el else None
            location = loc_el.get_text(strip=True) if loc_el else None
            salary = salary_el.get_text(" ", strip=True) if salary_el else None
            posted_date = posted_el.get_text(" ", strip=True) if posted_el else None
            work_type = work_type_el.get_text(" ", strip=True).lower() if work_type_el else None

            href_value = title_el.get("href") if title_el and title_el.name == "a" else None
            href = str(href_value) if href_value else None
            url = f"https://id.jobstreet.com{href}" if href and href.startswith("/") else href

            if title and company:
                job = empty_job(self.name, title, company)
                job["location"] = location
                job["url"] = url
                job["salary"] = salary
                job["posted_date"] = posted_date
                job["work_type"] = work_type
                results.append(job)
        return results
