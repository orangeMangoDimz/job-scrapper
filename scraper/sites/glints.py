from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from ..types import Job, empty_job
from ._api import request_json
from ._next_data import extract_next_data, walk_dicts
from .base import Scraper

# Glints' public GraphQL endpoint (v2-alc) powering the job-search page. No auth,
# but a WAF blocks non-browser clients — curl_cffi's Chrome impersonation is our
# best shot; we fall back to the __NEXT_DATA__ HTML (fetched via Playwright) if it
# blocks us. Reverse-engineered from glints.com/id search; may change.
_API_URL = "https://glints.com/api/v2-alc/graphql"
_COUNTRY = "ID"
_API_HEADERS = {
    "content-type": "application/json",
    "accept": "application/json",
    "origin": "https://glints.com",
    "referer": "https://glints.com/id/opportunities/jobs/explore",
}
_GRAPHQL_QUERY = """query searchJobsV3($data: JobSearchConditionInput!) {
  searchJobsV3(data: $data) {
    jobsInPage {
      id
      title
      company {
        name
        brandName
      }
      city {
        name
      }
      location {
        name
        formattedName
        administrativeLevelName
        parents {
          name
          formattedName
          administrativeLevelName
        }
      }
      country {
        code
        name
      }
      salaries {
        salaryType
        salaryMode
        maxAmount
        minAmount
        CurrencyCode
      }
      createdAt
      workArrangementOption
      type
      minYearsOfExperience
      maxYearsOfExperience
    }
    expInfo
    hasMore
  }
}"""


def _keyword_from_url(url: str) -> str:
    """Glints' HTML search URL carries the keyword in the `keyword` query param."""
    qs = parse_qs(urlparse(url).query)
    return (qs.get("keyword") or [""])[0].strip()


def _salary_from_api(salaries: object) -> str | None:
    if not isinstance(salaries, list) or not salaries:
        return None
    first = salaries[0]
    if not isinstance(first, dict):
        return None
    currency = first.get("CurrencyCode") or ""
    mode = first.get("salaryMode") or ""
    lo = first.get("minAmount")
    hi = first.get("maxAmount")
    if lo and hi:
        return f"{currency} {lo}-{hi} {mode}".strip()
    if lo:
        return f"{currency} {lo}+ {mode}".strip()
    return None


def _job_from_api(item: object) -> Job | None:
    """Map one searchJobsV3 result to the canonical Job shape."""
    if not isinstance(item, dict):
        return None
    title = item.get("title")
    job_id = item.get("id")
    company_node = item.get("company")
    company = None
    if isinstance(company_node, dict):
        company = company_node.get("name") or company_node.get("brandName")
    if not title or not job_id or not company:
        return None

    job = empty_job("glints", str(title).strip(), str(company).strip())
    job["job_id"] = str(job_id)
    job["url"] = f"https://glints.com/id/opportunities/jobs/{job_id}"

    # The API returns the location at District level (e.g. "Cipondoh") with the
    # City in `parents` — resolve to the City so it matches the wilayah location
    # filter, exactly like the __NEXT_DATA__ HTML parser does. Fall back to the
    # raw district name, then the (usually null) city node.
    location: str | None = None
    loc_node = item.get("location")
    if isinstance(loc_node, dict):
        location = (
            _city_name_from_hierarchical(loc_node)
            or loc_node.get("formattedName")
            or loc_node.get("name")
        )
    if not location:
        city = item.get("city")
        if isinstance(city, dict):
            location = city.get("name")
    job["location"] = str(location).strip() if location else None

    job["salary"] = _salary_from_api(item.get("salaries"))
    created_at = item.get("createdAt")
    job["posted_date"] = created_at if isinstance(created_at, str) else None

    # The API names these differently from the __NEXT_DATA__ payload, but the
    # candidate helpers already try the API spellings in their fallback chains.
    job["work_type"] = _work_type_from_candidate(item)
    job["employment_type"] = _employment_type_from_candidate(item)
    job["experience_level"] = _experience_level_from_candidate(item)
    return job


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
                return BeautifulSoup(description, "lxml").get_text("\n", strip=True)
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


# Listings that do not really specify experience come back as a wide-open span
# (0–50 observed), which says nothing useful — treat the upper bound as absent.
_EXPERIENCE_SENTINEL_YEARS = 20


def _experience_level_from_candidate(candidate: dict) -> str | None:
    for key in ("seniorityLevel", "experienceLevel", "experience"):
        value = candidate.get(key)
        if isinstance(value, str) and value:
            return _normalize(value)

    def _years(key: str) -> int | None:
        value = candidate.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return int(value)

    low = _years("minYearsOfExperience")
    high = _years("maxYearsOfExperience")
    if high is not None and high >= _EXPERIENCE_SENTINEL_YEARS:
        high = None
    if low is not None and high is not None:
        return f"{low}-{high} years" if high > low else f"{low}+ years"
    if low is not None:
        return None if low == 0 else f"{low}+ years"
    if high is not None:
        return f"up to {high} years"
    return None


class GlintsScraper(Scraper):
    name = "glints"
    # See JobstreetScraper: don't bail on an empty HTML fetch before the API runs.
    requires_search_html = False
    api_backed = True

    def collect(self, html: str) -> list[Job]:
        api_jobs = self._fetch_api_jobs()
        if api_jobs:
            return api_jobs
        # API failed/empty (or WAF-blocked) — fall back to __NEXT_DATA__ / HTML.
        return self.parse(html)

    def _fetch_api_jobs(self) -> list[Job]:
        keyword = _keyword_from_url(self.url)
        page_size = max(1, min(self.limit * self.max_pages, 100))
        variables = {
            "data": {
                "SearchTerm": keyword,
                "CountryCode": _COUNTRY,
                "includeExternalJobs": True,
                "pageSize": page_size,
                "page": 1,
            }
        }
        body = {"operationName": "searchJobsV3", "query": _GRAPHQL_QUERY, "variables": variables}
        payload = request_json(
            "POST", _API_URL, headers=_API_HEADERS, json_body=body, label="glints-api"
        )
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        node = data.get("searchJobsV3") if isinstance(data, dict) else None
        jobs_in_page = node.get("jobsInPage") if isinstance(node, dict) else None
        if not isinstance(jobs_in_page, list):
            return []
        results: list[Job] = []
        for item in jobs_in_page:
            job = _job_from_api(item)
            if job is not None:
                results.append(job)
        return results

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
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        soup = BeautifulSoup(html, "lxml")
        for selector in (".JobDescription", "[class*='description']", ".job-description"):
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
