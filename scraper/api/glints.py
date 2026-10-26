from __future__ import annotations

import threading
from typing import Any

from ..types import Job, empty_job
from .client import ApiClient, graphql_data
from .draftjs import draftjs_to_markdown
from .window import to_utc_iso

GRAPHQL_URL = "https://glints.com/api/v2-alc/graphql"
# visiting a page sets the `deviceid` cookie; without it searchJobsV3 ignores filters
WARM_URL = "https://glints.com/id/opportunities/jobs/explore?country=ID"
COUNTRY_CODE = "ID"
COUNTRY_ID = "7542a4d7-4324-4f76-ae1f-2e37ffb1198b"
# anonymous access: pageSize caps at 50 and page 2 returns NO_PERMISSION
MAX_PAGE_SIZE = 50
_COUNTRY_LEVEL = 1

SEARCH_QUERY = """
query searchJobsV3($data: JobSearchConditionInput!) {
  searchJobsV3(data: $data) {
    jobsInPage {
      id title createdAt type workArrangementOption
      minYearsOfExperience maxYearsOfExperience
      company { name }
      location { formattedName parents { formattedName level } }
      salaries { minAmount maxAmount CurrencyCode salaryMode }
    }
  }
}
"""

DETAIL_QUERY = """
query getJobById($id: String!) {
  getJobById(id: $id) { descriptionJsonString }
}
"""


def _location(node: Any) -> str | None:
    if not isinstance(node, dict) or not node.get("formattedName"):
        return None
    parents = [p for p in node.get("parents") or [] if isinstance(p, dict)]
    regional = sorted(
        (p for p in parents if (p.get("level") or 0) > _COUNTRY_LEVEL),
        key=lambda p: -(p.get("level") or 0),
    )
    names = [str(node["formattedName"])] + [str(p["formattedName"]) for p in regional]
    return ", ".join(dict.fromkeys(names))


def _salary(salaries: Any) -> str | None:
    if not isinstance(salaries, list) or not salaries or not isinstance(salaries[0], dict):
        return None
    first = salaries[0]
    low, high = first.get("minAmount"), first.get("maxAmount")
    if low is None and high is None:
        return None
    amount = " - ".join(f"{value:,}" for value in (low, high) if value is not None)
    currency = first.get("CurrencyCode") or ""
    mode = str(first.get("salaryMode") or "").lower()
    suffix = f" per {mode}" if mode else ""
    return f"{currency} {amount}{suffix}".strip()


def _experience(item: dict[str, Any]) -> str | None:
    low, high = item.get("minYearsOfExperience"), item.get("maxYearsOfExperience")
    if low is not None and high is not None:
        return f"{low}-{high} years"
    if low is not None:
        return f"{low}+ years"
    return None


def _lower(value: Any) -> str | None:
    return value.lower() if isinstance(value, str) and value else None


def _to_job(item: dict[str, Any]) -> Job | None:
    title = item.get("title")
    company = (
        (item.get("company") or {}).get("name") if isinstance(item.get("company"), dict) else None
    )
    if not title or not company:
        return None
    job = empty_job("glints", str(title).strip(), str(company).strip())
    job_id = str(item["id"]) if item.get("id") else None
    job["job_id"] = job_id
    job["url"] = f"https://glints.com/id/opportunities/jobs/{job_id}" if job_id else None
    job["location"] = _location(item.get("location"))
    job["salary"] = _salary(item.get("salaries"))
    job["posted_at"] = to_utc_iso(item.get("createdAt"))
    job["posted_date"] = job["posted_at"]
    job["employment_type"] = _lower(item.get("type"))
    job["work_type"] = _lower(item.get("workArrangementOption"))
    job["experience_level"] = _experience(item)
    return job


class GlintsApi:
    name = "glints"
    country_location: str | None = COUNTRY_ID

    def __init__(self, client: ApiClient) -> None:
        self._client = client
        self._is_warm = False
        # detail calls share this source across a thread pool: warm up exactly once
        self._warm_lock = threading.Lock()

    def _ensure_warm(self) -> None:
        if self._is_warm:
            return
        with self._warm_lock:
            if not self._is_warm:
                self._client.warm(WARM_URL)
                self._is_warm = True

    def _post(self, operation: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        self._ensure_warm()
        body = {"operationName": operation, "query": query, "variables": variables}
        return self._client.post_json(f"{GRAPHQL_URL}?op={operation}", body)

    def search(
        self, keyword: str, location: str | None, max_age_hours: int | None, limit: int
    ) -> list[Job]:
        # Glints has no date param; the runner's max-age filter on posted_at applies
        data = {
            "SearchTerm": keyword,
            "CountryCode": COUNTRY_CODE,
            "LocationIds": [location] if location else [],
            "page": 1,
            "pageSize": min(MAX_PAGE_SIZE, limit),
        }
        result = graphql_data(
            self._post("searchJobsV3", SEARCH_QUERY, {"data": data}), "searchJobsV3"
        )
        items = result.get("jobsInPage") or []
        return [job for item in items if isinstance(item, dict) and (job := _to_job(item))]

    def detail(self, job: Job) -> str | None:
        job_id = job.get("job_id")
        if not job_id:
            return None
        found = graphql_data(self._post("getJobById", DETAIL_QUERY, {"id": job_id}), "getJobById")
        return draftjs_to_markdown(found.get("descriptionJsonString"))
