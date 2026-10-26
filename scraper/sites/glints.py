from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from ..types import Job, empty_job
from ._markdown import html_to_markdown
from ._next_data import extract_next_data, walk_dicts
from .base import Scraper


def _city_name_from_hierarchical(node: dict | None) -> str | None:
    if not isinstance(node, dict):
        return None
    if node.get("administrativeLevelName") == "City":
        name = node.get("formattedName") or node.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    parents = node.get("parents")
    if isinstance(parents, list):
        for parent in parents:
            if isinstance(parent, dict) and parent.get("administrativeLevelName") == "City":
                name = parent.get("formattedName") or parent.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
    return None


def _description_from_jsonld(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if not tag.string:
            continue
        try:
            payload = json.loads(tag.string)
        except json.JSONDecodeError:
            continue
        for entry in payload if isinstance(payload, list) else [payload]:
            if not isinstance(entry, dict):
                continue
            if entry.get("@type") != "JobPosting":
                continue
            description = entry.get("description")
            if isinstance(description, str) and description.strip():
                return html_to_markdown(description)
    return None


def _company_from_candidate(candidate: dict) -> str | None:
    company = candidate.get("company")
    if isinstance(company, dict):
        return company.get("name")
    if isinstance(company, str):
        return company
    return candidate.get("companyName")


def _location_from_candidate(candidate: dict) -> str | None:
    for key in ("city", "location"):
        node = candidate.get(key)
        city_name = _city_name_from_hierarchical(node)
        if city_name:
            return city_name
    if candidate.get("locationName"):
        return candidate["locationName"]
    if candidate.get("cityName"):
        return candidate["cityName"]
    city = candidate.get("city")
    if isinstance(city, dict) and (city.get("name") or city.get("label")):
        return city.get("name") or city.get("label")
    location = candidate.get("location")
    if isinstance(location, dict):
        return location.get("name") or location.get("label")
    if isinstance(location, str):
        return location
    return None


def _salary_from_candidate(candidate: dict) -> str | None:
    salary = candidate.get("salary") or candidate.get("salaryEstimate")
    if isinstance(salary, dict):
        if isinstance(salary.get("displayText"), str):
            return salary["displayText"]
        currency = salary.get("currencyCode") or salary.get("currency") or ""
        min_amount = salary.get("minAmount") or salary.get("min")
        max_amount = salary.get("maxAmount") or salary.get("max")
        if min_amount and max_amount:
            return f"{currency} {min_amount}-{max_amount}".strip()
        if min_amount:
            return f"{currency} {min_amount}".strip()
    if isinstance(salary, str):
        return salary
    return None


def _posted_date_from_candidate(candidate: dict) -> str | None:
    for key in ("publishedAt", "createdAt", "updatedAt", "postedAt"):
        value = candidate.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _normalize(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _work_type_from_candidate(candidate: dict) -> str | None:
    for key in ("workArrangementOption", "workType", "remoteType"):
        value = candidate.get(key)
        if isinstance(value, str) and value:
            return _normalize(value)
    return None


def _employment_type_from_candidate(candidate: dict) -> str | None:
    for key in ("jobType", "type", "employmentType"):
        value = candidate.get(key)
        if isinstance(value, str) and value:
            return _normalize(value)
    return None


def _experience_level_from_candidate(candidate: dict) -> str | None:
    for key in ("seniorityLevel", "experienceLevel", "experience"):
        value = candidate.get(key)
        if isinstance(value, str) and value:
            return _normalize(value)
    if isinstance(candidate.get("minYearsOfExperience"), int | float):
        years = int(candidate["minYearsOfExperience"])
        return f"{years}+ years"
    return None


class GlintsScraper(Scraper):
    name = "glints"

    def parse_detail(self, html: str) -> str | None:
        jsonld_description = _description_from_jsonld(html)
        if jsonld_description:
            return jsonld_description
        data = extract_next_data(html)
        if data:
            candidates: list[dict] = []
            walk_dicts(
                data,
                lambda d: any(k in d for k in ("description", "requirements", "jobDescription")),
                candidates,
            )
            for candidate in candidates:
                for key in ("description", "requirements", "jobDescription"):
                    value = candidate.get(key)
                    text = html_to_markdown(value) if isinstance(value, str) else None
                    if text:
                        return text
        soup = BeautifulSoup(html, "lxml")
        for selector in (".JobDescription", "[class*='description']", ".job-description"):
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
            lambda d: ("title" in d) and ("company" in d or "companyName" in d),
            candidates,
        )
        results: list[Job] = []
        seen: set[tuple[str, str]] = set()
        for candidate in candidates:
            title = candidate.get("title")
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
            slug = candidate.get("slug") or candidate.get("id")
            job["job_id"] = str(slug) if slug else None
            job["url"] = f"https://glints.com/id/opportunities/jobs/{slug}" if slug else None
            job["salary"] = _salary_from_candidate(candidate)
            job["posted_date"] = _posted_date_from_candidate(candidate)
            job["work_type"] = _work_type_from_candidate(candidate)
            job["employment_type"] = _employment_type_from_candidate(candidate)
            job["experience_level"] = _experience_level_from_candidate(candidate)

            results.append(job)
        return results

    def _parse_html(self, html: str) -> list[Job]:
        soup = BeautifulSoup(html, "lxml")
        anchors = soup.select("a[href*='/opportunities/jobs/']")
        seen_urls: set[str] = set()
        results: list[Job] = []
        for anchor in anchors:
            href_value = anchor.get("href") or ""
            href = str(href_value)
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)
            title_el = anchor.select_one("h2,h3,h4") or anchor
            title = title_el.get_text(" ", strip=True)
            container = anchor.find_parent()
            company_el = (
                container.find(class_=re.compile(r"CompanyName", re.I)) if container else None
            )
            loc_el = (
                container.find(class_=re.compile(r"Location|Place|City", re.I))
                if container
                else None
            )
            salary_el = container.find(class_=re.compile(r"Salary", re.I)) if container else None
            company = company_el.get_text(" ", strip=True) if company_el else None
            location = loc_el.get_text(" ", strip=True) if loc_el else None
            salary = salary_el.get_text(" ", strip=True) if salary_el else None
            url = href if href.startswith("http") else f"https://glints.com{href}"
            if title and company:
                job = empty_job(self.name, title, company)
                job["location"] = location
                job["url"] = url
                job["salary"] = salary
                results.append(job)
        return results
