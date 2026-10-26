from __future__ import annotations

import uuid
from typing import Any

from ..sites._markdown import html_to_markdown
from ..types import Job, empty_job
from .client import ApiClient, ApiError, graphql_data
from .window import days_window, to_utc_iso

SEARCH_URL = "https://id.jobstreet.com/api/jobsearch/v5/search"
DETAIL_URL = "https://id.jobstreet.com/graphql"
SITE_KEY = "ID-Main"
LOCALE = "id-ID"
MAX_PAGE_SIZE = 100
MAX_PAGES = 5
DETAIL_HEADERS = {"seek-request-brand": "jobstreet", "seek-request-country": "ID"}

# every declared variable must be used, or SEEK rejects the query
DETAIL_QUERY = """
query jobDetails($jobId: ID!, $jobDetailsViewedCorrelationId: String!, $sessionId: String!) {
  jobDetails(
    id: $jobId
    tracking: {channel: "WEB", jobDetailsViewedCorrelationId: $jobDetailsViewedCorrelationId, sessionId: $sessionId}
  ) {
    job { content(platform: WEB) }
  }
}
"""


def _company(item: dict[str, Any]) -> str | None:
    advertiser = item.get("advertiser")
    if isinstance(advertiser, dict) and advertiser.get("description"):
        return str(advertiser["description"])
    name = item.get("companyName")
    return str(name) if name else None


def _location(item: dict[str, Any]) -> str | None:
    locations = item.get("locations")
    if isinstance(locations, list) and locations and isinstance(locations[0], dict):
        label = locations[0].get("label")
        return str(label) if label else None
    return None


def _employment_type(item: dict[str, Any]) -> str | None:
    work_types = item.get("workTypes")
    if isinstance(work_types, list) and work_types and isinstance(work_types[0], str):
        return work_types[0].lower()
    return None


def _work_type(item: dict[str, Any]) -> str | None:
    arrangements = item.get("workArrangements")
    data = arrangements.get("data") if isinstance(arrangements, dict) else None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        label = data[0].get("label")
        text = label.get("text") if isinstance(label, dict) else None
        return text.lower() if isinstance(text, str) else None
    return None


def _to_job(item: dict[str, Any]) -> Job | None:
    title = item.get("title")
    company = _company(item)
    if not title or not company:
        return None
    job = empty_job("jobstreet", str(title).strip(), company.strip())
    job_id = str(item["id"]) if item.get("id") else None
    job["job_id"] = job_id
    job["url"] = f"https://id.jobstreet.com/id/job/{job_id}" if job_id else None
    job["location"] = _location(item)
    job["salary"] = item.get("salaryLabel") or None
    job["posted_at"] = to_utc_iso(item.get("listingDate"))
    job["posted_date"] = item.get("listingDateDisplay") or None
    job["employment_type"] = _employment_type(item)
    job["work_type"] = _work_type(item)
    return job


class JobstreetApi:
    name = "jobstreet"
    country_location: str | None = None  # no `where` param = all of Indonesia

    def __init__(self, client: ApiClient) -> None:
        self._client = client

    def _params(
        self, keyword: str, location: str | None, max_age_hours: int | None, page: int, size: int
    ) -> dict[str, str]:
        params = {
            "siteKey": SITE_KEY,
            "keywords": keyword.lower(),  # search is case-sensitive; HTML slug was lowercase
            "locale": LOCALE,
            "page": str(page),
            "pageSize": str(size),
        }
        if location:
            params["where"] = location
        days = days_window(max_age_hours)
        if days is not None:
            params["daterange"] = str(days)
        return params

    def search(
        self, keyword: str, location: str | None, max_age_hours: int | None, limit: int
    ) -> list[Job]:
        size = min(MAX_PAGE_SIZE, limit)
        jobs: list[Job] = []
        for page in range(1, MAX_PAGES + 1):
            payload = self._client.get_json(
                SEARCH_URL, params=self._params(keyword, location, max_age_hours, page, size)
            )
            items = payload.get("data")
            if not isinstance(items, list):
                raise ApiError("bad_shape", "search response has no data list")
            jobs.extend(job for item in items if isinstance(item, dict) and (job := _to_job(item)))
            if len(items) < size or len(jobs) >= limit:
                break
        return jobs[:limit]

    def detail(self, job: Job) -> str | None:
        job_id = job.get("job_id")
        if not job_id:
            return None
        body = {
            "operationName": "jobDetails",
            "query": DETAIL_QUERY,
            "variables": {
                "jobId": job_id,
                "jobDetailsViewedCorrelationId": str(uuid.uuid4()),
                "sessionId": str(uuid.uuid4()),
            },
        }
        payload = self._client.post_json(DETAIL_URL, body, headers=DETAIL_HEADERS)
        details = graphql_data(payload, "jobDetails")
        content = ((details or {}).get("job") or {}).get("content")
        return html_to_markdown(content) if isinstance(content, str) else None
