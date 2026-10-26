from __future__ import annotations

from bs4 import BeautifulSoup

from ..types import Job, empty_job
from ._markdown import html_to_markdown
from ._next_data import extract_next_data, walk_dicts
from .base import Scraper


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
                    text = html_to_markdown(value) if isinstance(value, str) else None
                    if text:
                        return text
        soup = BeautifulSoup(html, "lxml")
        for selector in (
            "[data-automation='jobAdDetails']",
            "[data-automation='jobDescription']",
            ".job-description",
        ):
            el = soup.select_one(selector)
            if el:
                text = html_to_markdown(str(el))
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
            lambda d: (
                ("jobTitle" in d or "title" in d)
                and ("companyName" in d or "advertiser" in d or "company" in d)
            ),
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
