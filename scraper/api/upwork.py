from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from ..types import Job, empty_job
from .client import ApiClient, ApiError, graphql_data
from .window import to_utc_iso

HOME_URL = "https://www.upwork.com/"
GRAPHQL_URL = "https://www.upwork.com/api/graphql/v1"
JOB_URL_PREFIX = "https://www.upwork.com/jobs/"
TOKEN_COOKIE = "visitor_gql_token"
PAGE_SIZE = 50  # Upwork caps paging.count at 50
MAX_OFFSET = 5000  # deep offsets stop returning jobs
COMPANY_NAME = "Upwork Client"  # visitor search exposes no client data
LOCATION = "Remote"
WORK_TYPE = "remote"
CURRENCY = "USD"
FIXED = "FIXED"

SEARCH_QUERY = """
query VisitorJobSearch($requestVariables: VisitorJobSearchV1Request!) {
  search {
    universalSearchNuxt {
      visitorJobSearchV1(request: $requestVariables) {
        paging { total offset count }
        results {
          id
          title
          description
          ontologySkills { prefLabel }
          jobTile {
            job {
              id
              ciphertext: cipherText
              jobType
              hourlyBudgetMax
              hourlyBudgetMin
              contractorTier
              publishTime
              fixedPriceAmount { amount }
            }
          }
        }
      }
    }
  }
}
"""

HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "Referer": "https://www.upwork.com/nx/search/jobs/?",
    "X-Upwork-Accept-Language": "en-US",
}


def _money(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _budget(value: Any) -> float | None:
    """Upwork sends budgets as numbers or numeric text. 0 is not a real budget."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0 < number < math.inf else None


def _pay_numbers(job: dict[str, Any]) -> tuple[float | None, float | None]:
    if job.get("jobType") == FIXED:
        amount = _budget((job.get("fixedPriceAmount") or {}).get("amount"))
        return amount, amount
    low = _budget(job.get("hourlyBudgetMin"))
    high = _budget(job.get("hourlyBudgetMax"))
    if low is None:
        return high, high
    return low, low if high is None else high


def _salary(job: dict[str, Any], low: float | None, high: float | None) -> str | None:
    if low is None or high is None:
        return None
    if job.get("jobType") == FIXED:
        return f"{CURRENCY} {_money(low)} fixed"
    if low == high:
        return f"{CURRENCY} {_money(low)} per hour"
    return f"{CURRENCY} {_money(low)} - {_money(high)} per hour"


def _requirements(item: dict[str, Any]) -> str | None:
    description = (item.get("description") or "").strip()
    skills = [
        str(skill["prefLabel"])
        for skill in item.get("ontologySkills") or []
        if isinstance(skill, dict) and skill.get("prefLabel")
    ]
    skill_line = f"Skills: {', '.join(skills)}" if skills else ""
    return "\n\n".join(part for part in (description, skill_line) if part) or None


def _lower(value: Any) -> str | None:
    return value.lower() if isinstance(value, str) and value else None


def _tier(value: Any) -> str | None:
    """Live values are EntryLevel, IntermediateLevel and ExpertLevel."""
    tier = _lower(value)
    return tier.removesuffix("level") if tier else None


def _to_job(item: dict[str, Any]) -> Job | None:
    details = (item.get("jobTile") or {}).get("job") or {}
    title, cipher = item.get("title"), details.get("ciphertext")
    if not title or not cipher:
        return None
    job = empty_job("upwork", str(title).strip(), COMPANY_NAME)
    low, high = _pay_numbers(details)
    job["job_id"] = str(item["id"]) if item.get("id") else None
    job["url"] = f"{JOB_URL_PREFIX}{cipher}"
    job["location"] = LOCATION
    job["work_type"] = WORK_TYPE
    job["employment_type"] = _lower(details.get("jobType"))
    job["salary"] = _salary(details, low, high)
    job["salary_min"], job["salary_max"] = low, high
    job["experience_level"] = _tier(details.get("contractorTier"))
    job["requirements"] = _requirements(item)
    job["posted_at"] = to_utc_iso(details.get("publishTime"))
    job["posted_date"] = job["posted_at"]
    return job


def _is_older(job: Job, cutoff: datetime | None) -> bool:
    posted = job.get("posted_at")
    if cutoff is None or posted is None:
        return False
    return datetime.fromisoformat(posted) < cutoff


class UpworkApi:
    name = "upwork"
    country_location: str | None = None

    def __init__(self, client: ApiClient) -> None:
        self._client = client
        self._token: str | None = None

    def _ensure_token(self) -> str:
        if self._token is None:
            self._token = self._client.get_cookie(HOME_URL, TOKEN_COOKIE)
        if not self._token:
            raise ApiError("token_missing")
        return self._token

    def _fetch_page(self, keyword: str, offset: int) -> list[Any]:
        variables = {
            "requestVariables": {
                "sort": "recency",
                "highlight": False,
                "userQuery": keyword,
                "paging": {"offset": offset, "count": PAGE_SIZE},
            }
        }
        headers = {**HEADERS, "Authorization": f"Bearer {self._ensure_token()}"}
        payload = self._client.post_json(
            GRAPHQL_URL, {"query": SEARCH_QUERY, "variables": variables}, headers=headers
        )
        search = graphql_data(payload, "search").get("universalSearchNuxt") or {}
        result = search.get("visitorJobSearchV1")
        if not isinstance(result, dict):
            raise ApiError("graphql_error", "missing visitorJobSearchV1")
        return result.get("results") or []

    def search(
        self, keyword: str, location: str | None, max_age_hours: int | None, limit: int
    ) -> list[Job]:
        # every job is remote, so `location` is ignored
        cutoff = None
        if max_age_hours is not None:
            cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
        jobs: list[Job] = []
        for offset in range(0, MAX_OFFSET, PAGE_SIZE):
            items = self._fetch_page(keyword, offset)
            page = [job for item in items if isinstance(item, dict) and (job := _to_job(item))]
            jobs.extend(page)
            # recency sort: one old job means every later page is older too
            has_old_job = any(_is_older(job, cutoff) for job in page)
            if len(jobs) >= limit or len(items) < PAGE_SIZE or has_old_job:
                break
        return jobs[:limit]

    def detail(self, job: Job) -> str | None:
        return None  # search already returns the full description
