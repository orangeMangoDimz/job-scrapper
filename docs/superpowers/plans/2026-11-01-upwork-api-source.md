# Upwork API-Only Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Upwork as a scraper platform reachable through MCP, fetched only from Upwork's visitor GraphQL API with no HTML path, and add Upwork-only Job type and Salary dropdowns to the Job Match filter bar.

**Architecture:** A new `scraper/api/upwork.py` source collects `visitor_gql_token` from the homepage and pages `VisitorJobSearch`. A new `api_only` flag on `Scraper` makes the runner report an error instead of falling back to HTML, and skips job-page requirement fetches. Numeric `salary_min` and `salary_max` travel from the scraper through Mongo to the backend and frontend, so the latest-jobs query can filter pay on the server and keep paging correct.

**Tech Stack:** Python 3.12+, curl_cffi, pytest, FastMCP, Django REST Framework, MongoDB aggregation, Vue 3, Pinia, Vitest.

**Commits:** The user asked for no commits until they say so. Leave changes uncommitted on the current branches. Do not create worktrees.

---

## Agreed design (from the grilling session)

| Topic | Decision |
|---|---|
| Fetch method | `GET https://www.upwork.com/` for `visitor_gql_token`, then `POST https://www.upwork.com/api/graphql/v1` with `Authorization: Bearer <token>`. |
| HTML | Never. No search fallback, no job-page fetch for requirements. |
| Failure | Write an error payload. MCP lists Upwork in `errors` with 0 jobs. Other sites keep running. No retry. |
| Token | One token per (site, keyword) run. The token is tied to the IP, and one `ApiClient` session uses one proxy for both calls. |
| Paging | 50 per page (Upwork's cap), until `limit` is reached, a job is older than `max_age_hours`, or a short page arrives. |
| Limit | `limit: 30` for Upwork only. |
| Keywords | Global `keywords`. |
| Proxy | Global `proxy`. |
| Enabled | `enabled: true` in `config.yaml` after the smoke run passes. `enabled: false` in the dev patch. |
| `company` | `Upwork Client` for every job. |
| `company_id` | `None`. |
| `url` | `https://www.upwork.com/jobs/<ciphertext>` |
| `job_id` | Upwork `id`. |
| `location` / `work_type` | `Remote` / `remote`. Site-level `filter: {}` bypasses the global location filter. |
| `employment_type` | `hourly` or `fixed`. |
| `salary` | `USD 18 - 45 per hour`, `USD 500 fixed`, or `None`. |
| `salary_min` / `salary_max` | New numeric fields. A fixed job has both equal to the amount. One hourly bound fills both. |
| `experience_level` | `entry`, `intermediate`, or `expert`, from `contractorTier`. |
| `requirements` | Full description, blank line, `Skills: a, b`. |
| Dropdown spot | Job Match filter bar, shown only when Platform is `upwork`. |
| Job type options | All, Hourly, Fixed. |
| Salary options | Follow Job type. Disabled until Hourly or Fixed is chosen. Hourly: under $25, $25-50, $50-100, $100+. Fixed: under $500, $500-2k, $2k-10k, $10k+. |
| Range match | Overlap: `salary_max >= at_least` and `salary_min < below`. |
| No budget | Hidden while a range is selected. |
| Small links | `upwork` label, `upwork.com` in `COMPANY_DOMAIN_BLOCKLIST`, README and prompt site lists. |
| Licensing | `asaniczka/Upwork-Job-Scraper` has no license. Use it as a guide. Copy no code from it. |

## Verified API facts (tested 2026-11-01 with curl_cffi, direct IP, no login)

- `GET /` returns 200 and sets `visitor_gql_token` (45 chars).
- Variables: `{"requestVariables": {"sort": "recency", "highlight": false, "userQuery": "python", "paging": {"offset": 0, "count": 50}}}`.
- `userQuery` filters. `q` fails with a `ValidationError`.
- `paging.count` above 50 is capped: asking for 100 returned 50.
- Offset 100 worked. `total` for `software engineer` was 494, sorted newest first.
- Introspection is disabled: `"Introspection query is disabled for this client"`.
- `upworkHistoryData`, `personsToHire` are undefined on this schema, so client data is not available.
- `publishTime` looks like `2026-11-01T10:13:32.065Z`.
- Some jobs have no budget at all.

Not verified until the smoke run: the proxy path, `contractorTier` values, repeated use at scale.

## File structure

| File | Responsibility |
|---|---|
| Modify `scraper/scraper/types.py` | Add `salary_min`, `salary_max`. |
| Modify `scraper/scraper/api/client.py` | Add `get_cookie`. |
| Modify `scraper/tests/api_fakes.py` | `FakeResponse.cookies`. |
| Create `scraper/scraper/api/upwork.py` | `UpworkApi`: token, paging, mapping. |
| Create `scraper/scraper/sites/upwork.py` | `UpworkScraper` stub with `api_only = True`. |
| Modify `scraper/scraper/sites/base.py` | `api_only` flag. |
| Modify `scraper/scraper/sites/__init__.py`, `scraper/scraper/api/registry.py` | Register `upwork`. |
| Modify `scraper/scraper/runner.py` | API-only failure path, no page fetch. |
| Modify `scraper/scraper/config_loader.py` | Allow `www.upwork.com`. |
| Modify `scraper/config.yaml`, `scraper/config.dev.patch.yaml`, `scraper/config.dev.patch.yaml.example` | Site entry. |
| Modify `scraper/README.md`, `scraper/prompts/scrape-and-post.md` | Site lists. |
| Create `scraper/tests/test_api_upwork.py`, `scraper/tests/test_runner_api_only.py` | Tests. |
| Modify `backend/src/shared/dto/job.py` | `salary_min`, `salary_max`, `PayFilter`. |
| Modify `backend/src/shared/enums/job.py` | `JobPayType`. |
| Modify `backend/src/shared/database/abstract/scraper.py`, `backend/src/shared/database/mongo/database.py`, `backend/src/shared/database/mongo/pipeline.py` | `pay` filter. |
| Modify `backend/src/api/schema/jobs.py`, `backend/src/api/routes/jobs.py` | Query params, salary fields. |
| Modify `backend/src/shared/constants/company.py` | Blocklist. |
| Modify `backend/src/shared/tests/fake_health.py`, `backend/src/api/tests/test_latest_jobs.py`, `backend/src/shared/tests/test_mongo_scraped_jobs.py` | Tests. |
| Modify `frontend/src/modules/job-match/domain/entities/JobFilters.ts`, `ScrapedJob.ts` | Filters, ranges, salary numbers. |
| Modify `frontend/src/modules/job-match/data/models/ScrapeRunModel.ts`, `data/datasources/JobScrapeRemoteDataSource.ts` | Mapping, query params. |
| Modify `frontend/src/modules/job-match/presentation/stores/useJobFiltersStore.ts`, `presentation/components/JobFiltersBar.vue`, `presentation/composables/jobLabels.ts` | State, dropdowns, label. |

---

# Part 1: Scraper

Run scraper commands from `scraper/` with `.venv/bin/python -m pytest`.

### Task 1: Salary fields on `Job`

**Files:**
- Modify: `scraper/scraper/types.py`
- Modify: `scraper/config.yaml` (`default_fields`)
- Test: `scraper/tests/test_api_upwork.py`

- [ ] **Step 1: Write the failing test**

Create `scraper/tests/test_api_upwork.py`:

```python
from __future__ import annotations

from scraper.types import JOB_FIELD_ORDER, empty_job


def test_empty_job_has_empty_salary_numbers():
    job = empty_job("upwork", "Role", "Upwork Client")

    assert job["salary_min"] is None
    assert job["salary_max"] is None
    assert list(job) == list(JOB_FIELD_ORDER)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_api_upwork.py -v`
Expected: FAIL with `KeyError: 'salary_min'`

- [ ] **Step 3: Write minimal implementation**

In `scraper/scraper/types.py`, add to `class Job` after `salary: str | None`:

```python
    salary_min: float | None
    salary_max: float | None
```

Add to `JOB_FIELD_ORDER` after `"salary",`:

```python
    "salary_min",
    "salary_max",
```

Add to `empty_job` after `salary=None,`:

```python
        salary_min=None,
        salary_max=None,
```

In `scraper/config.yaml`, add to `default_fields` after `- salary`:

```yaml
  - salary_min
  - salary_max
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api_upwork.py tests/test_scrape_jobs_ok.py -v`
Expected: PASS

### Task 2: `ApiClient.get_cookie`

**Files:**
- Modify: `scraper/tests/api_fakes.py`
- Modify: `scraper/scraper/api/client.py`
- Test: `scraper/tests/test_api_client.py`

- [ ] **Step 1: Write the failing test**

In `scraper/tests/api_fakes.py`, replace `FakeResponse.__init__`:

```python
    def __init__(
        self,
        status_code: int = 200,
        payload: Any = None,
        text: str = "",
        cookies: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.cookies = cookies or {}
```

Append to `scraper/tests/test_api_client.py`:

```python
def test_get_cookie_reads_the_response_cookie():
    client, session = make_client([FakeResponse(cookies={"token": "abc"})])

    assert client.get_cookie("https://example.test/", "token") == "abc"
    assert session.calls[0][0] == "GET"


def test_get_cookie_returns_none_when_the_cookie_is_missing():
    client, _ = make_client([FakeResponse()])

    assert client.get_cookie("https://example.test/", "token") is None
```

Add these imports to `tests/test_api_client.py` if they are missing: `from tests.api_fakes import FakeResponse, make_client`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_api_client.py -v -k get_cookie`
Expected: FAIL with `AttributeError: 'ApiClient' object has no attribute 'get_cookie'`

- [ ] **Step 3: Write minimal implementation**

In `scraper/scraper/api/client.py`, add after `warm`:

```python
    def get_cookie(self, url: str, name: str) -> str | None:
        return self._request("GET", url).cookies.get(name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_api_client.py -v`
Expected: PASS

### Task 3: `UpworkApi`

**Files:**
- Create: `scraper/scraper/api/upwork.py`
- Test: `scraper/tests/test_api_upwork.py`

- [ ] **Step 1: Write the failing tests**

Replace the imports at the top of `scraper/tests/test_api_upwork.py` and append the tests:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scraper.api.client import ApiError
from scraper.api.upwork import COMPANY_NAME, GRAPHQL_URL, HOME_URL, PAGE_SIZE, UpworkApi
from scraper.types import JOB_FIELD_ORDER, empty_job
from tests.api_fakes import FakeResponse, make_client

TOKEN_RESPONSE = FakeResponse(cookies={"visitor_gql_token": "tok"})


def _iso(hours_ago: float = 1) -> str:
    moment = datetime.now(UTC) - timedelta(hours=hours_ago)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _item(job_id: str = "1", hours_ago: float = 1, **job_overrides):
    job = {
        "id": job_id,
        "ciphertext": f"~{job_id}",
        "jobType": "HOURLY",
        "hourlyBudgetMin": 18.0,
        "hourlyBudgetMax": 45.0,
        "contractorTier": "ExpertLevel",
        "publishTime": _iso(hours_ago),
        "fixedPriceAmount": None,
    }
    job.update(job_overrides)
    return {
        "id": job_id,
        "title": "Voice AI Agent Developer",
        "description": "Build voice agents.",
        "ontologySkills": [{"prefLabel": "Python"}, {"prefLabel": "Vapi"}],
        "jobTile": {"job": job},
    }


def _page(items, total=None):
    return FakeResponse(
        payload={
            "data": {
                "search": {
                    "universalSearchNuxt": {
                        "visitorJobSearchV1": {
                            "paging": {"total": total or len(items), "offset": 0, "count": 50},
                            "results": items,
                        }
                    }
                }
            }
        }
    )


def test_search_fetches_the_token_then_sends_it_as_bearer():
    client, session = make_client([TOKEN_RESPONSE, _page([_item()])])

    UpworkApi(client).search("python", "Remote", 72, 30)

    assert session.calls[0][:2] == ("GET", HOME_URL)
    method, url, kwargs = session.calls[1]
    assert (method, url) == ("POST", GRAPHQL_URL)
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    request = kwargs["json"]["variables"]["requestVariables"]
    assert request["userQuery"] == "python"
    assert request["sort"] == "recency"
    assert request["paging"] == {"offset": 0, "count": PAGE_SIZE}


def test_search_maps_an_hourly_job():
    client, _ = make_client([TOKEN_RESPONSE, _page([_item("7")])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["site"] == "upwork"
    assert job["company"] == COMPANY_NAME
    assert job["company_id"] is None
    assert job["job_id"] == "7"
    assert job["url"] == "https://www.upwork.com/jobs/~7"
    assert job["location"] == "Remote"
    assert job["work_type"] == "remote"
    assert job["employment_type"] == "hourly"
    assert job["salary"] == "USD 18 - 45 per hour"
    assert (job["salary_min"], job["salary_max"]) == (18.0, 45.0)
    assert job["experience_level"] == "expertlevel"
    assert job["requirements"] == "Build voice agents.\n\nSkills: Python, Vapi"
    assert job["posted_at"] == job["posted_date"]
    assert job["posted_at"].endswith("+00:00")


def test_search_maps_a_fixed_job():
    item = _item(
        jobType="FIXED",
        hourlyBudgetMin=None,
        hourlyBudgetMax=None,
        fixedPriceAmount={"amount": 500.0},
    )
    client, _ = make_client([TOKEN_RESPONSE, _page([item])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["employment_type"] == "fixed"
    assert job["salary"] == "USD 500 fixed"
    assert (job["salary_min"], job["salary_max"]) == (500.0, 500.0)


def test_search_leaves_salary_empty_without_a_budget():
    item = _item(hourlyBudgetMin=None, hourlyBudgetMax=None)
    client, _ = make_client([TOKEN_RESPONSE, _page([item])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["salary"] is None
    assert (job["salary_min"], job["salary_max"]) == (None, None)


def test_search_fills_both_salary_numbers_from_one_hourly_bound():
    item = _item(hourlyBudgetMin=30.0, hourlyBudgetMax=None)
    client, _ = make_client([TOKEN_RESPONSE, _page([item])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["salary"] == "USD 30 per hour"
    assert (job["salary_min"], job["salary_max"]) == (30.0, 30.0)


def test_search_treats_a_zero_budget_as_no_budget():
    item = _item(jobType="FIXED", fixedPriceAmount={"amount": 0})
    client, _ = make_client([TOKEN_RESPONSE, _page([item])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["salary"] is None
    assert (job["salary_min"], job["salary_max"]) == (None, None)


def test_search_writes_large_budgets_in_full():
    item = _item(jobType="FIXED", fixedPriceAmount={"amount": 1000000.0})
    client, _ = make_client([TOKEN_RESPONSE, _page([item])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["salary"] == "USD 1,000,000 fixed"


def test_search_keeps_the_description_alone_without_skills():
    item = _item()
    item["ontologySkills"] = None
    client, _ = make_client([TOKEN_RESPONSE, _page([item])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["requirements"] == "Build voice agents."


def test_search_skips_an_item_without_a_title_or_ciphertext():
    no_title = _item("1")
    no_title["title"] = ""
    no_cipher = _item("2", ciphertext=None)
    client, _ = make_client([TOKEN_RESPONSE, _page([no_title, no_cipher, _item("3")])])

    jobs = UpworkApi(client).search("python", "Remote", 72, 30)

    assert [job["job_id"] for job in jobs] == ["3"]


def test_search_pages_until_the_limit_with_one_token():
    first = [_item(str(i)) for i in range(PAGE_SIZE)]
    second = [_item(str(i + PAGE_SIZE)) for i in range(PAGE_SIZE)]
    client, session = make_client([TOKEN_RESPONSE, _page(first), _page(second)])

    jobs = UpworkApi(client).search("python", "Remote", 72, 60)

    assert len(jobs) == 60
    assert len(session.calls) == 3
    second_request = session.calls[2][2]["json"]["variables"]["requestVariables"]
    assert second_request["paging"]["offset"] == PAGE_SIZE


def test_search_stops_after_a_short_page():
    client, session = make_client([TOKEN_RESPONSE, _page([_item()])])

    UpworkApi(client).search("python", "Remote", 72, 60)

    assert len(session.calls) == 2


def test_search_stops_paging_once_jobs_pass_max_age():
    fresh_then_stale = [_item(str(i), hours_ago=i * 2) for i in range(PAGE_SIZE)]
    client, session = make_client([TOKEN_RESPONSE, _page(fresh_then_stale)])

    jobs = UpworkApi(client).search("python", "Remote", 72, 200)

    assert len(session.calls) == 2
    assert len(jobs) == PAGE_SIZE


def test_search_pages_without_max_age_until_the_limit():
    first = [_item(str(i), hours_ago=500) for i in range(PAGE_SIZE)]
    client, session = make_client([TOKEN_RESPONSE, _page(first), _page([_item("x")])])

    jobs = UpworkApi(client).search("python", "Remote", None, 200)

    assert len(session.calls) == 3
    assert len(jobs) == PAGE_SIZE + 1


def test_search_raises_when_the_token_cookie_is_missing():
    client, session = make_client([FakeResponse()])

    with pytest.raises(ApiError) as error:
        UpworkApi(client).search("python", "Remote", 72, 30)

    assert error.value.code == "token_missing"
    assert len(session.calls) == 1


def test_search_raises_on_graphql_errors():
    client, _ = make_client(
        [TOKEN_RESPONSE, FakeResponse(payload={"errors": [{"message": "bad"}]})]
    )

    with pytest.raises(ApiError) as error:
        UpworkApi(client).search("python", "Remote", 72, 30)

    assert error.value.code == "graphql_error"


def test_search_raises_when_the_result_is_missing():
    empty = FakeResponse(payload={"data": {"search": {"universalSearchNuxt": {}}}})
    client, _ = make_client([TOKEN_RESPONSE, empty])

    with pytest.raises(ApiError) as error:
        UpworkApi(client).search("python", "Remote", 72, 30)

    assert error.value.code == "graphql_error"


def test_search_raises_on_a_blocked_token_request():
    client, _ = make_client([FakeResponse(status_code=403, text="blocked")])

    with pytest.raises(ApiError) as error:
        UpworkApi(client).search("python", "Remote", 72, 30)

    assert error.value.code == "http_403"


def test_detail_sends_nothing():
    client, session = make_client([])

    assert UpworkApi(client).detail(empty_job("upwork", "Role", COMPANY_NAME)) is None
    assert session.calls == []
```

Keep `test_empty_job_has_empty_salary_numbers` from Task 1.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api_upwork.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.api.upwork'`

- [ ] **Step 3: Write minimal implementation**

Create `scraper/scraper/api/upwork.py`:

```python
from __future__ import annotations

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


def _pay_numbers(job: dict[str, Any]) -> tuple[float | None, float | None]:
    # `or None`: a budget of 0 is not a real budget
    if job.get("jobType") == FIXED:
        amount = (job.get("fixedPriceAmount") or {}).get("amount") or None
        return amount, amount
    low = job.get("hourlyBudgetMin") or None
    high = job.get("hourlyBudgetMax") or None
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
    job["experience_level"] = _lower(details.get("contractorTier"))
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api_upwork.py -v`
Expected: PASS

### Task 4: API-only runner path and site registration

**Files:**
- Modify: `scraper/scraper/sites/base.py`
- Create: `scraper/scraper/sites/upwork.py`
- Modify: `scraper/scraper/sites/__init__.py`
- Modify: `scraper/scraper/api/registry.py`
- Modify: `scraper/scraper/runner.py`
- Test: `scraper/tests/test_runner_api_only.py`

- [ ] **Step 1: Write the failing tests**

Create `scraper/tests/test_runner_api_only.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from scraper.api.client import ApiError
from scraper.api.registry import API_SOURCES
from scraper.api.upwork import UpworkApi
from scraper.runner import run_one
from scraper.sites import SCRAPERS
from scraper.sites.upwork import UpworkScraper
from scraper.types import empty_job

FIELDS = frozenset({"site", "matched_keyword", "title", "company", "url", "requirements"})
URL = "https://www.upwork.com/nx/search/jobs/?q=python"


def _scraper() -> UpworkScraper:
    return UpworkScraper(url=URL, limit=30)


def _run(tmp_path: Path, fetcher: MagicMock, api_search, api_detail=None) -> None:
    run_one(
        _scraper(),
        fetcher,
        tmp_path,
        "python",
        FIELDS,
        None,
        {},
        api_search=api_search,
        api_detail=api_detail,
    )


def _job() -> dict:
    job = empty_job("upwork", "Role", "Upwork Client")
    job["url"] = "https://www.upwork.com/jobs/~1"
    return job


def test_upwork_is_registered():
    assert SCRAPERS["upwork"] is UpworkScraper
    assert API_SOURCES["upwork"] is UpworkApi


def test_scraper_is_api_only_and_parses_nothing():
    assert _scraper().api_only is True
    assert _scraper().parse("<html></html>") == []


def test_api_error_writes_an_error_and_never_fetches_html(tmp_path: Path):
    fetcher = MagicMock()

    def _fail():
        raise ApiError("http_403", "blocked")

    _run(tmp_path, fetcher, _fail)

    payload = json.loads((tmp_path / "upwork.json").read_text())
    assert payload["error"] == "api failed: http_403"
    assert payload["source"] == "api"
    assert "blocked" not in json.dumps(payload)
    raw = json.loads((tmp_path / "upwork.raw.json").read_text())
    assert raw["count"] == 0
    fetcher.fetch.assert_not_called()


def test_unexpected_exception_writes_an_error_and_never_fetches_html(tmp_path: Path):
    fetcher = MagicMock()

    def _crash():
        raise KeyError("shape")

    _run(tmp_path, fetcher, _crash)

    payload = json.loads((tmp_path / "upwork.json").read_text())
    assert payload["error"] == "api failed: unexpected_error:KeyError"
    fetcher.fetch.assert_not_called()


def test_missing_api_search_writes_an_error_and_never_fetches_html(tmp_path: Path):
    fetcher = MagicMock()

    _run(tmp_path, fetcher, None)

    payload = json.loads((tmp_path / "upwork.json").read_text())
    assert payload["error"] == "api failed: api_disabled"
    fetcher.fetch.assert_not_called()


def test_blank_requirements_never_fetch_the_job_page(tmp_path: Path):
    fetcher = MagicMock()

    _run(tmp_path, fetcher, lambda: [_job()], lambda _job: None)

    payload = json.loads((tmp_path / "upwork.json").read_text())
    assert payload["count"] == 1
    fetcher.fetch.assert_not_called()


def test_zero_results_is_not_an_error(tmp_path: Path):
    _run(tmp_path, MagicMock(), lambda: [])

    payload = json.loads((tmp_path / "upwork.json").read_text())
    assert "error" not in payload
    assert payload["count"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_runner_api_only.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.sites.upwork'`

- [ ] **Step 3: Write minimal implementation**

In `scraper/scraper/sites/base.py`, add to `class Scraper` after `requires_search_html: bool = True`:

```python
    # True: the runner never fetches or parses HTML for this site
    api_only: bool = False
```

Create `scraper/scraper/sites/upwork.py`:

```python
from __future__ import annotations

from ..types import Job
from .base import Scraper


class UpworkScraper(Scraper):
    """Registers Upwork with the runner. All data comes from scraper/api/upwork.py."""

    name = "upwork"
    requires_search_html = False
    api_only = True

    def parse(self, html: str) -> list[Job]:
        return []
```

In `scraper/scraper/sites/__init__.py`:
- Add `from .upwork import UpworkScraper` after the `linkedin` import.
- Change the tuple to `(JobstreetScraper, GlintsScraper, LinkedinScraper, IndeedScraper, UpworkScraper)`.
- Add `"UpworkScraper",` to `__all__`.

In `scraper/scraper/api/registry.py`:
- Add `from .upwork import UpworkApi` after the `source` import.
- Add `"upwork": UpworkApi,` to `API_SOURCES`.

In `scraper/scraper/runner.py`, add before `def _html_jobs`:

```python
def _write_api_failure(json_path: Path, raw_path: Path, keyword: str, reason: str) -> None:
    error = f"api failed: {reason}"
    json_path.write_text(
        json.dumps(
            {
                "error": error,
                "keyword": keyword,
                "source": "api",
                "fallback_reason": None,
            },
            indent=2,
        )
    )
    # same reset as _html_jobs: a stale raw file must not be credited to this run
    raw_path.write_text(
        json.dumps({"keyword": keyword, "count": 0, "jobs": [], "error": error}, indent=2)
    )
```

In `_fetch_requirements`, change the first guard to:

```python
    if "requirements" not in fields or not jobs or scraper.api_only:
        return
```

In `run_one`, change both log lines in the `except` branches:

```python
            _LOG.warning("[%s] api failed (%s)", label, exc.code)
```

```python
            _LOG.exception("[%s] api crashed", label)
```

In `run_one`, add directly before `if jobs is None:`:

```python
    if jobs is None and scraper.api_only:
        _write_api_failure(json_path, raw_path, keyword, fallback_reason or "api_disabled")
        return
```

The existing `MagicMock` scrapers in `tests/test_runner_bail.py` make `scraper.api_only` truthy. Set `scraper.api_only = False` in every `MagicMock` scraper those tests build. Find them with `grep -rn 'scraper = MagicMock()' tests`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_runner_api_only.py tests/test_runner_api.py tests/test_runner_bail.py tests/test_runner_raw.py -v`
Expected: PASS

### Task 5: Config

**Files:**
- Modify: `scraper/scraper/config_loader.py`
- Modify: `scraper/config.yaml`
- Modify: `scraper/config.dev.patch.yaml`
- Modify: `scraper/config.dev.patch.yaml.example`
- Test: `scraper/tests/test_config_api.py`

- [ ] **Step 1: Write the failing test**

Append to `scraper/tests/test_config_api.py`, adding `from pathlib import Path` and `from scraper.config_loader import load` if they are missing:

```python
def test_upwork_site_bypasses_the_global_location_filter(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
keywords: [python]
filter:
  location: [jakarta]
sites:
  upwork:
    limit: 30
    filter: {}
    url_template: "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency"
    api:
      locations: [Remote]
"""
    )

    config = load(config_path)

    assert config.filter_for("upwork") == {}
    assert config.limit_for("upwork") == 30
    assert config.site("upwork").api.locations == ("Remote",)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_config_api.py -v -k upwork`
Expected: FAIL with `ConfigError: site 'upwork' url_template has disallowed host 'www.upwork.com'`

- [ ] **Step 3: Write minimal implementation**

In `scraper/scraper/config_loader.py`, add `"www.upwork.com",` to `ALLOWED_URL_HOSTS`.

In `scraper/config.yaml`, add under `sites:` after `indeed`. Keep `enabled: false` until Task 7 passes:

```yaml
  upwork:
    enabled: false
    limit: 30
    # all jobs are remote and worldwide, so the global Indonesian location filter is off
    filter: {}
    # never fetched: Upwork is API-only. The runner still requires a url_template.
    url_template: "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency"
    api:
      enabled: true
      # search_all needs one entry to make one call. UpworkApi ignores the value.
      locations: [Remote]
      country_wide: false
```

In `scraper/config.dev.patch.yaml` and `scraper/config.dev.patch.yaml.example`, add under `sites:`:

```yaml
  upwork:
    enabled: false
    limit: 3
    url_template: "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_config_api.py -v`
Expected: PASS

### Task 6: Docs and full scraper suite

**Files:**
- Modify: `scraper/README.md`
- Modify: `scraper/prompts/scrape-and-post.md`

- [ ] **Step 1: Update the site lists**

In `scraper/prompts/scrape-and-post.md` line 16, change the example to:

```json
  "requested_sites": ["jobstreet", "glints", "linkedin", "indeed", "upwork"],
```

In `scraper/README.md`, add Upwork wherever sites are listed, with this note. Find the places with `grep -n -i 'glints' README.md`:

```markdown
Upwork is API-only. It uses the visitor GraphQL endpoint with no login and has no HTML fallback, so a failure shows up in `errors` with 0 jobs.
```

- [ ] **Step 2: Run the full scraper suite**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check . && .venv/bin/mypy scraper mcp_server`
Expected: all pass

### Task 7: Live smoke run

**Files:**
- Modify: `scraper/config.yaml`

- [ ] **Step 1: Run one small live search through the proxy config**

Run from `scraper/`:

```bash
.venv/bin/python -c "
from pathlib import Path
from scraper.config_loader import load
from scraper.runner import run
print(run(load(Path('config.yaml')), targets=['upwork'], keywords=['software engineer']))
"
```

Expected: prints `0`. `output/software-engineer/upwork.json` has `count` above 0, `source` is `api`, and no `error` key.

If `socks5://localhost:1080` is not running, repeat with `config.dev.patch.yaml` applied or `proxy` removed in a temporary copy, and record in the handoff that the proxy path stayed untested.

- [ ] **Step 2: Check the data**

Open `output/software-engineer/upwork.json`. Confirm `url` opens a real job, `salary` and `salary_min` agree, and record the real `experience_level` values. If the values are unreadable like `expertlevel`, tell the user before mapping them.

- [ ] **Step 3: Enable the site**

In `scraper/config.yaml`, change the Upwork `enabled: false` to `enabled: true`.

# Part 2: Backend

Run backend commands from `backend/`, with the same test command the repo uses: `cd src && python -m pytest <path>`.

### Task 8: Salary numbers on the job DTO and API

**Files:**
- Modify: `backend/src/shared/dto/job.py`
- Modify: `backend/src/api/schema/jobs.py`
- Test: `backend/src/api/tests/test_latest_jobs.py`

- [ ] **Step 1: Write the failing test**

In `backend/src/api/tests/test_latest_jobs.py`, change the imports to `from dataclasses import fields, replace` and `from shared.dto.job import Job, ScrapeRunPage`, then append:

```python
def test_latest_jobs_returns_the_salary_numbers(
    fake_scraper_database: FakeScraperDatabase, auth_headers: dict[str, str]
) -> None:
    job = Job(site="upwork", salary="USD 18 - 45 per hour", salary_min=18.0, salary_max=45.0)
    page = build_page()
    fake_scraper_database.latest_page = replace(
        page, scrape_run=replace(page.scrape_run, jobs=(job,))
    )

    response = Client().get(JOBS_URL, headers=auth_headers)

    [body] = response.json()["data"]["jobs"]
    assert body["salary_min"] == 18.0
    assert body["salary_max"] == 45.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && python -m pytest api/tests/test_latest_jobs.py -v -k salary_numbers`
Expected: FAIL with `TypeError` on the unexpected keyword `salary_min`

- [ ] **Step 3: Write minimal implementation**

In `backend/src/shared/dto/job.py`, add to `class Job` after `salary: str | None = None`:

```python
    salary_min: float | None = None
    salary_max: float | None = None
```

In `backend/src/api/schema/jobs.py`, add to `JobSerializer` after `salary`:

```python
    salary_min = serializers.FloatField(allow_null=True)
    salary_max = serializers.FloatField(allow_null=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && python -m pytest api/tests/test_latest_jobs.py -v`
Expected: PASS

### Task 9: Pay filter in the latest-jobs query

**Files:**
- Modify: `backend/src/shared/enums/job.py`
- Modify: `backend/src/shared/dto/job.py`
- Modify: `backend/src/shared/database/abstract/scraper.py`
- Modify: `backend/src/shared/database/mongo/database.py`
- Modify: `backend/src/shared/database/mongo/pipeline.py`
- Modify: `backend/src/shared/tests/fake_health.py`
- Modify: `backend/src/api/schema/jobs.py`
- Modify: `backend/src/api/routes/jobs.py`
- Test: `backend/src/api/tests/test_latest_jobs.py`
- Test: `backend/src/shared/tests/test_mongo_scraped_jobs.py`

- [ ] **Step 1: Write the failing API tests**

Append to `backend/src/api/tests/test_latest_jobs.py`. Change the imports to `from shared.dto.job import Job, PayFilter, ScrapeRunPage` and `from shared.enums.job import JobPayType, JobRegion`:

```python
def test_latest_jobs_passes_the_pay_filter_from_the_query(
    fake_scraper_database: FakeScraperDatabase, auth_headers: dict[str, str]
) -> None:
    fake_scraper_database.latest_page = build_page()

    response = Client().get(
        f"{JOBS_URL}?employment_type=hourly&salary_gte=25&salary_lt=50", headers=auth_headers
    )

    assert response.status_code == 200
    assert fake_scraper_database.pay_requests == [
        PayFilter(employment_type=JobPayType.HOURLY, salary_gte=25.0, salary_lt=50.0)
    ]


def test_latest_jobs_sends_no_pay_filter_by_default(
    fake_scraper_database: FakeScraperDatabase, auth_headers: dict[str, str]
) -> None:
    fake_scraper_database.latest_page = build_page()

    Client().get(JOBS_URL, headers=auth_headers)

    assert fake_scraper_database.pay_requests == [None]


def test_latest_jobs_rejects_an_unknown_employment_type(
    fake_scraper_database: FakeScraperDatabase, auth_headers: dict[str, str]
) -> None:
    response = Client().get(f"{JOBS_URL}?employment_type=weekly", headers=auth_headers)

    assert response.status_code == 400


def test_latest_jobs_rejects_a_negative_salary(
    fake_scraper_database: FakeScraperDatabase, auth_headers: dict[str, str]
) -> None:
    response = Client().get(f"{JOBS_URL}?salary_gte=-1", headers=auth_headers)

    assert response.status_code == 400
```

- [ ] **Step 2: Write the failing Mongo tests**

Append to `backend/src/shared/tests/test_mongo_scraped_jobs.py`. Add `from shared.dto.job import PayFilter`, and change the enum import to `from shared.enums.job import JobPayType, JobRegion`:

```python
def build_pay_job(job_id: str, kind: str, low: float | None, high: float | None) -> dict[str, Any]:
    return {
        "site": "upwork",
        "url": f"https://jobs.test/{job_id}",
        "employment_type": kind,
        "salary_min": low,
        "salary_max": high,
    }


PAY_JOBS = [
    build_pay_job("h1", "hourly", 18, 45),
    build_pay_job("h2", "hourly", 60, 80),
    build_pay_job("h3", "hourly", None, None),
    build_pay_job("f1", "fixed", 500, 500),
]


def read_pay_urls(
    scraper_db: tuple[Database, MongoScraperDatabase], pay: PayFilter
) -> list[str | None]:
    mongo, database = scraper_db
    mongo.scrape_runs.insert_one(build_one_site_run(NEWER_RUN_AT, "upwork", PAY_JOBS))
    page = database.find_latest_scrape_run(limit=10, offset=0, pay=pay)
    assert page is not None
    return [job.url for job in page.scrape_run.jobs]


def test_find_latest_scrape_run_keeps_only_jobs_of_the_employment_type(
    scraper_db: tuple[Database, MongoScraperDatabase],
) -> None:
    urls = read_pay_urls(scraper_db, PayFilter(employment_type=JobPayType.FIXED))

    assert urls == ["https://jobs.test/f1"]


def test_find_latest_scrape_run_keeps_pay_that_overlaps_the_range(
    scraper_db: tuple[Database, MongoScraperDatabase],
) -> None:
    pay = PayFilter(employment_type=JobPayType.HOURLY, salary_gte=25, salary_lt=50)

    assert read_pay_urls(scraper_db, pay) == ["https://jobs.test/h1"]


def test_find_latest_scrape_run_hides_jobs_without_a_budget_below_a_ceiling(
    scraper_db: tuple[Database, MongoScraperDatabase],
) -> None:
    pay = PayFilter(employment_type=JobPayType.HOURLY, salary_lt=25)

    assert read_pay_urls(scraper_db, pay) == ["https://jobs.test/h1"]


def test_find_latest_scrape_run_keeps_the_top_range_without_a_ceiling(
    scraper_db: tuple[Database, MongoScraperDatabase],
) -> None:
    pay = PayFilter(employment_type=JobPayType.HOURLY, salary_gte=50)

    assert read_pay_urls(scraper_db, pay) == ["https://jobs.test/h2"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd src && python -m pytest api/tests/test_latest_jobs.py -v -k 'pay or employment or negative'`
Expected: FAIL with `ImportError: cannot import name 'PayFilter'`

- [ ] **Step 4: Write minimal implementation**

In `backend/src/shared/enums/job.py`, add after `JobType`:

```python
class JobPayType(ChoiceEnum):
    HOURLY = "hourly"
    FIXED = "fixed"
```

In `backend/src/shared/dto/job.py`, add `from shared.enums.job import JobPayType` to the imports, and add after `class Job`:

```python
@dataclass(frozen=True)
class PayFilter:
    """Keeps jobs of a pay type whose pay overlaps [salary_gte, salary_lt)."""

    employment_type: JobPayType | None = None
    salary_gte: float | None = None
    salary_lt: float | None = None

    @property
    def has_range(self) -> bool:
        return self.salary_gte is not None or self.salary_lt is not None
```

In `backend/src/shared/database/abstract/scraper.py`, import `PayFilter`, add `pay: PayFilter | None = None` as the last parameter of `find_latest_scrape_run`, and add this sentence to its docstring after the region sentence:

```text
        A pay filter keeps the jobs of its employment type whose pay overlaps its range.
        Jobs without a budget are left out while a range is set.
```

In `backend/src/shared/database/mongo/database.py`, import `PayFilter`, add `pay: PayFilter | None = None` as the last parameter of `find_latest_scrape_run`, and change the pipeline call:

```python
        rows = self._aggregate(
            self.job_pipeline.build_page(limit, offset, keyword, site, region, pay)
        )
```

In `backend/src/shared/database/mongo/pipeline.py`:

Add the import `from shared.dto.job import PayFilter` and the constant after `OLDEST_FIRST`:

```python
NUMBER_TYPES = ["double", "int", "long", "decimal"]
```

Add `pay: PayFilter | None = None` as the last parameter of `build_page`, and change its match call:

```python
            *self._build_job_stages(self._build_job_match(keyword, site, region, pay)),
```

Replace `_build_job_match`:

```python
    def _build_job_match(
        self,
        keyword: str | None,
        site: str | None,
        region: JobRegion | None,
        pay: PayFilter | None = None,
    ) -> dict[str, Any]:
        conditions = [
            {"$eq": [{"$toLower": self._build_text_or_null(field)}, wanted.lower()]}
            for field, wanted in (("$matched_keyword", keyword), ("$site", site))
            if wanted is not None
        ]
        if region is not None:
            conditions.append(self._build_region_match(region))
        if pay is not None:
            conditions.extend(self._build_pay_match(pay))
        return {"$expr": {"$and": conditions}} if conditions else {}

    def _build_pay_match(self, pay: PayFilter) -> list[dict[str, Any]]:
        conditions: list[dict[str, Any]] = []
        if pay.employment_type is not None:
            wanted = pay.employment_type.value
            field = self._build_text_or_null("$employment_type")
            conditions.append({"$eq": [{"$toLower": field}, wanted]})
        if pay.has_range:
            conditions.append({"$in": [{"$type": "$salary_min"}, NUMBER_TYPES]})
            conditions.append({"$in": [{"$type": "$salary_max"}, NUMBER_TYPES]})
        if pay.salary_gte is not None:
            conditions.append({"$gte": ["$salary_max", pay.salary_gte]})
        if pay.salary_lt is not None:
            conditions.append({"$lt": ["$salary_min", pay.salary_lt]})
        return conditions
```

In `backend/src/shared/tests/fake_health.py`, import `PayFilter`, add to `__init__`:

```python
        self.pay_requests: list[PayFilter | None] = []
```

Add `pay: PayFilter | None = None` as the last parameter of `find_latest_scrape_run`, and add after `self.region_requests.append(region)`:

```python
        self.pay_requests.append(pay)
```

In `backend/src/api/schema/jobs.py`, import `JobPayType`, and add to `LatestJobsQuerySerializer` after `location`:

```python
    employment_type = serializers.ChoiceField(choices=JobPayType.list_choices(), required=False)
    salary_gte = serializers.FloatField(min_value=0, required=False)
    salary_lt = serializers.FloatField(min_value=0, required=False)
```

Add this method after `validate_location`:

```python
    def validate_employment_type(self, employment_type: str) -> JobPayType:
        return JobPayType(employment_type)
```

In `backend/src/api/routes/jobs.py`, import `PayFilter`, add `PAY_QUERY_FIELDS = ("employment_type", "salary_gte", "salary_lt")` after `SITE_NAME_REGEX`, and add this helper:

```python
def build_pay_filter(page_query: dict) -> PayFilter | None:
    pay_query = {field: page_query[field] for field in PAY_QUERY_FIELDS if field in page_query}
    return PayFilter(**pay_query) if pay_query else None
```

Pass it in `LatestJobsView.get`:

```python
            region=page_query.get("location"),
            pay=build_pay_filter(page_query),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd src && python -m pytest api/tests/test_latest_jobs.py shared/tests -v`
Expected: PASS. Mongo tests skip unless `MONGO_TEST_URI` is set. Set it and run `shared/tests/test_mongo_scraped_jobs.py` if a local Mongo is available, otherwise report them as not run.

### Task 10: Company blocklist

**Files:**
- Modify: `backend/src/shared/constants/company.py`

- [ ] **Step 1: Add the domain**

In `COMPANY_DOMAIN_BLOCKLIST`, add `"upwork.com",` after `"indeed.com",`.

- [ ] **Step 2: Run the backend suite**

Run: `cd src && python -m pytest -q`
Expected: PASS

# Part 3: Frontend

Run frontend commands from `frontend/`. Always use `--exclude '.claude/**'` with vitest.

### Task 11: Salary numbers on `ScrapedJob`

**Files:**
- Modify: `frontend/src/modules/job-match/domain/entities/ScrapedJob.ts`
- Modify: `frontend/src/modules/job-match/data/models/ScrapeRunModel.ts`
- Modify: `frontend/src/modules/job-match/presentation/stores/__tests__/scrapeFixtures.ts`
- Test: `frontend/src/modules/job-match/data/models/__tests__/ScrapeRunModel.spec.ts`

- [ ] **Step 1: Write the failing tests**

Append to `ScrapeRunModel.spec.ts`, reusing its `jobModel` and `runModel` builders:

```ts
describe('toScrapeRun salary numbers', () => {
  it('maps the salary numbers and keeps missing ones empty', () => {
    const run = toScrapeRun(
      runModel({
        jobs: [
          jobModel({ job_id: 'a', salary_min: 18, salary_max: 45 }),
          jobModel({ job_id: 'b' }),
        ],
      }),
    )

    expect(run.jobs[0]).toMatchObject({ salaryMin: 18, salaryMax: 45 })
    expect(run.jobs[1]).toMatchObject({ salaryMin: null, salaryMax: null })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run --exclude '.claude/**' src/modules/job-match/data/models/__tests__/ScrapeRunModel.spec.ts`
Expected: FAIL, `salaryMin` is undefined

- [ ] **Step 3: Write minimal implementation**

In `ScrapedJob.ts`, add after `salary: string | null`:

```ts
  salaryMin: number | null
  salaryMax: number | null
```

In `ScrapeRunModel.ts`, add to `ScrapedJobModel` after `salary`:

```ts
  salary_min?: number | null
  salary_max?: number | null
```

Add after `optionalText`:

```ts
function optionalNumber(value: unknown, label: string): number | null {
  if (value === null || value === undefined) {
    return null
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${label} must be a number`)
  }
  return value
}
```

In `toScrapedJob`, add to `fields` after `salary`:

```ts
    salaryMin: optionalNumber(model.salary_min, `${label} salary min`),
    salaryMax: optionalNumber(model.salary_max, `${label} salary max`),
```

In `scrapeFixtures.ts`, add to `buildScrapedJob` after `salary: '$50/hr',`:

```ts
    salaryMin: null,
    salaryMax: null,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run --exclude '.claude/**' src/modules/job-match/data/models/__tests__/ScrapeRunModel.spec.ts`
Expected: PASS

### Task 12: Filter entity

**Files:**
- Modify: `frontend/src/modules/job-match/domain/entities/JobFilters.ts`
- Test: `frontend/src/modules/job-match/domain/entities/__tests__/JobFilters.spec.ts`

- [ ] **Step 1: Write the failing tests**

Append to `JobFilters.spec.ts`, and import `findSalaryRange`, `SALARY_RANGES`:

```ts
describe('pay filters', () => {
  const hourly = { ...NO_JOB_FILTERS, site: 'upwork', employmentType: 'hourly' as const }
  const job = buildScrapedJob({
    site: 'upwork',
    employmentType: 'hourly',
    salaryMin: 18,
    salaryMax: 45,
  })

  it('reports the pay filters as filters', () => {
    expect(hasJobFilters({ ...NO_JOB_FILTERS, employmentType: 'fixed' })).toBe(true)
    expect(hasJobFilters({ ...NO_JOB_FILTERS, salaryRange: 'hourly-25-50' })).toBe(true)
  })

  it('offers four ranges for each job type', () => {
    expect(SALARY_RANGES.hourly.map((range) => range.label)).toEqual([
      'Under $25/hr',
      '$25-50/hr',
      '$50-100/hr',
      '$100+/hr',
    ])
    expect(SALARY_RANGES.fixed.map((range) => range.label)).toEqual([
      'Under $500',
      '$500-2k',
      '$2k-10k',
      '$10k+',
    ])
  })

  it('finds a range by its value', () => {
    expect(findSalaryRange('hourly-25-50')?.atLeast).toBe(25)
    expect(findSalaryRange('missing')).toBeUndefined()
    expect(findSalaryRange(null)).toBeUndefined()
  })

  it('matches the job type', () => {
    expect(matchesJobFilters(job, hourly, locations)).toBe(true)
    expect(matchesJobFilters(job, { ...hourly, employmentType: 'fixed' }, locations)).toBe(false)
  })

  it('matches pay that overlaps the range', () => {
    const filters = { ...hourly, salaryRange: 'hourly-25-50' }

    expect(matchesJobFilters(job, filters, locations)).toBe(true)
    expect(
      matchesJobFilters(job, { ...hourly, salaryRange: 'hourly-50-100' }, locations),
    ).toBe(false)
  })

  it('hides a job without a budget while a range is set', () => {
    const noBudget = buildScrapedJob({ site: 'upwork', employmentType: 'hourly' })
    const filters = { ...hourly, salaryRange: 'hourly-0-25' }

    expect(matchesJobFilters(noBudget, filters, locations)).toBe(false)
    expect(matchesJobFilters(noBudget, hourly, locations)).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run --exclude '.claude/**' src/modules/job-match/domain/entities/__tests__/JobFilters.spec.ts`
Expected: FAIL, `SALARY_RANGES` is undefined

- [ ] **Step 3: Write minimal implementation**

In `JobFilters.ts`, replace the `JobFilters` interface, `NO_JOB_FILTERS`, and `hasJobFilters`, and replace `matchesJobFilters`:

```ts
export const PAY_FILTER_SITE = 'upwork'

export type JobPayType = 'hourly' | 'fixed'

export interface SalaryRange {
  value: string
  label: string
  atLeast: number | null
  below: number | null
}

export const SALARY_RANGES: Record<JobPayType, SalaryRange[]> = {
  hourly: [
    { value: 'hourly-0-25', label: 'Under $25/hr', atLeast: null, below: 25 },
    { value: 'hourly-25-50', label: '$25-50/hr', atLeast: 25, below: 50 },
    { value: 'hourly-50-100', label: '$50-100/hr', atLeast: 50, below: 100 },
    { value: 'hourly-100-up', label: '$100+/hr', atLeast: 100, below: null },
  ],
  fixed: [
    { value: 'fixed-0-500', label: 'Under $500', atLeast: null, below: 500 },
    { value: 'fixed-500-2k', label: '$500-2k', atLeast: 500, below: 2000 },
    { value: 'fixed-2k-10k', label: '$2k-10k', atLeast: 2000, below: 10000 },
    { value: 'fixed-10k-up', label: '$10k+', atLeast: 10000, below: null },
  ],
}

export interface JobFilters {
  site: string | null
  location: string | null
  employmentType: JobPayType | null
  salaryRange: string | null
}

export const NO_JOB_FILTERS: JobFilters = {
  site: null,
  location: null,
  employmentType: null,
  salaryRange: null,
}

export function hasJobFilters(filters: JobFilters): boolean {
  return Object.values(filters).some((value) => value !== null)
}

export function findSalaryRange(value: string | null): SalaryRange | undefined {
  return Object.values(SALARY_RANGES)
    .flat()
    .find((range) => range.value === value)
}

function matchesSalaryRange(job: ScrapedJob, range: SalaryRange): boolean {
  if (job.salaryMin === null || job.salaryMax === null) {
    return false
  }
  return (
    (range.atLeast === null || job.salaryMax >= range.atLeast) &&
    (range.below === null || job.salaryMin < range.below)
  )
}

function matchesPay(job: ScrapedJob, filters: JobFilters): boolean {
  if (filters.employmentType !== null && job.employmentType?.toLowerCase() !== filters.employmentType) {
    return false
  }
  const range = findSalaryRange(filters.salaryRange)
  return range === undefined || matchesSalaryRange(job, range)
}

export function matchesJobFilters(
  job: ScrapedJob,
  filters: JobFilters,
  options: JobLocationOption[],
): boolean {
  if (filters.site !== null && job.site.toLowerCase() !== filters.site) {
    return false
  }
  if (!matchesPay(job, filters)) {
    return false
  }
  return filters.location === null || matchesLocation(job.location, filters.location, options)
}
```

Keep `OTHER_LOCATION`, `JobLocationOption`, `JobFilterOptions`, `namesAnyPlace`, and `matchesLocation` unchanged.

- [ ] **Step 4: Fix existing literals**

Run: `npx vue-tsc --noEmit`
For each error that names a `JobFilters` literal such as `{ site: 'linkedin', location: null }`, change it to spread defaults: `{ ...NO_JOB_FILTERS, site: 'linkedin' }`, importing `NO_JOB_FILTERS` from the entity. For `JobScrapeRepositoryImpl.spec.ts`, use `{ ...NO_JOB_FILTERS, site: 'linkedin', location: 'jakarta' }`. For the job-builder errors in specs with hand-written `ScrapedJob` objects, add `salaryMin: null, salaryMax: null`.

- [ ] **Step 5: Run test to verify it passes**

Run: `npx vitest run --exclude '.claude/**' src/modules/job-match/domain/entities/__tests__/JobFilters.spec.ts`
Expected: PASS

### Task 13: Query params

**Files:**
- Modify: `frontend/src/modules/job-match/data/datasources/JobScrapeRemoteDataSource.ts`
- Test: `frontend/src/modules/job-match/data/datasources/__tests__/JobScrapeRemoteDataSource.spec.ts`

- [ ] **Step 1: Write the failing tests**

In `JobScrapeRemoteDataSource.spec.ts`, add `import { NO_JOB_FILTERS } from '@/modules/job-match/domain/entities/JobFilters'`, then append inside `describe('JobScrapeRemoteDataSource')`:

```ts
  it('sends the job type and salary range', async () => {
    const getWithMeta = vi.fn<HttpClient['getWithMeta']>().mockResolvedValue({} as never)
    const dataSource = new JobScrapeRemoteDataSource({ getWithMeta } as unknown as HttpClient)

    await dataSource.getLatestJobs(10, 0, {
      ...NO_JOB_FILTERS,
      site: 'upwork',
      employmentType: 'hourly',
      salaryRange: 'hourly-25-50',
    })

    expect(getWithMeta).toHaveBeenCalledWith(
      '/jobs?limit=10&offset=0&site=upwork&employment_type=hourly&salary_gte=25&salary_lt=50',
    )
  })

  it('leaves out the open end of a salary range', async () => {
    const getWithMeta = vi.fn<HttpClient['getWithMeta']>().mockResolvedValue({} as never)
    const dataSource = new JobScrapeRemoteDataSource({ getWithMeta } as unknown as HttpClient)

    await dataSource.getLatestJobs(10, 0, { ...NO_JOB_FILTERS, salaryRange: 'hourly-100-up' })

    expect(getWithMeta).toHaveBeenCalledWith('/jobs?limit=10&offset=0&salary_gte=100')
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run --exclude '.claude/**' src/modules/job-match/data/datasources/__tests__/JobScrapeRemoteDataSource.spec.ts`
Expected: FAIL, the URL has no `employment_type`

- [ ] **Step 3: Write minimal implementation**

In `JobScrapeRemoteDataSource.ts`, change the entity import to include `findSalaryRange`:

```ts
import { findSalaryRange, type JobFilters } from '@/modules/job-match/domain/entities/JobFilters'
```

Add after the `location` block in `getLatestJobs`:

```ts
    if (filters.employmentType !== null) {
      query.set('employment_type', filters.employmentType)
    }
    const range = findSalaryRange(filters.salaryRange)
    if (range?.atLeast != null) {
      query.set('salary_gte', String(range.atLeast))
    }
    if (range?.below != null) {
      query.set('salary_lt', String(range.below))
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run --exclude '.claude/**' src/modules/job-match/data/datasources/__tests__/JobScrapeRemoteDataSource.spec.ts`
Expected: PASS

### Task 14: Store and dropdowns

**Files:**
- Modify: `frontend/src/modules/job-match/presentation/stores/useJobFiltersStore.ts`
- Modify: `frontend/src/modules/job-match/presentation/components/JobFiltersBar.vue`
- Modify: `frontend/src/modules/job-match/presentation/composables/jobLabels.ts`
- Test: `frontend/src/modules/job-match/presentation/stores/__tests__/useJobFiltersStore.spec.ts`
- Create: `frontend/src/modules/job-match/presentation/components/__tests__/JobFiltersBar.spec.ts`

- [ ] **Step 1: Write the failing store tests**

Append inside `describe('useJobFiltersStore')`:

```ts
  it('clears the job type and salary range when the platform leaves upwork', () => {
    const store = useJobFiltersStore()
    store.setSite('upwork')
    store.setEmploymentType('hourly')
    store.setSalaryRange('hourly-25-50')

    store.setSite('linkedin')

    expect(store.filters.employmentType).toBeNull()
    expect(store.filters.salaryRange).toBeNull()
  })

  it('clears the salary range when the job type changes', () => {
    const store = useJobFiltersStore()
    store.setSite('upwork')
    store.setEmploymentType('hourly')
    store.setSalaryRange('hourly-25-50')

    store.setEmploymentType('fixed')

    expect(store.filters.employmentType).toBe('fixed')
    expect(store.filters.salaryRange).toBeNull()
  })

  it('shows the pay filters only for upwork', () => {
    const store = useJobFiltersStore()

    expect(store.showsPayFilters).toBe(false)
    store.setSite('upwork')
    expect(store.showsPayFilters).toBe(true)
  })
```

- [ ] **Step 2: Write the failing component tests**

Create `frontend/src/modules/job-match/presentation/components/__tests__/JobFiltersBar.spec.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import JobFiltersBar from '@/modules/job-match/presentation/components/JobFiltersBar.vue'
import { useJobFiltersStore } from '@/modules/job-match/presentation/stores/useJobFiltersStore'

vi.mock('@/shared/composables/useMinimumLoading', async () => {
  const { ref } = await import('vue')
  return { useMinimumLoading: () => ref(false) }
})

const AppSelectStub = {
  name: 'AppSelect',
  props: ['modelValue', 'options', 'disabled'],
  template: '<div data-testid="select" :data-disabled="disabled" />',
}

function mountBar() {
  return mount(JobFiltersBar, { global: { stubs: { AppSelect: AppSelectStub } } })
}

describe('JobFiltersBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const store = useJobFiltersStore()
    store.status = 'ready'
    store.sites = ['linkedin', 'upwork']
  })

  it('hides the pay dropdowns for other platforms', () => {
    const wrapper = mountBar()

    expect(wrapper.findAll('[data-testid="select"]')).toHaveLength(2)
  })

  it('shows the pay dropdowns for upwork with the salary disabled', async () => {
    const store = useJobFiltersStore()
    store.setSite('upwork')
    const wrapper = mountBar()
    await wrapper.vm.$nextTick()

    const selects = wrapper.findAll('[data-testid="select"]')
    expect(selects).toHaveLength(4)
    expect(selects[3].attributes('data-disabled')).toBe('true')
  })

  it('enables the salary dropdown with the ranges of the job type', async () => {
    const store = useJobFiltersStore()
    store.setSite('upwork')
    store.setEmploymentType('fixed')
    const wrapper = mountBar()
    await wrapper.vm.$nextTick()

    const salary = wrapper.findAllComponents(AppSelectStub)[3]
    expect(salary.props('disabled')).toBe(false)
    expect(salary.props('options').map((option: { label: string }) => option.label)).toEqual([
      'All salaries',
      'Under $500',
      '$500-2k',
      '$2k-10k',
      '$10k+',
    ])
  })
})
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `npx vitest run --exclude '.claude/**' src/modules/job-match/presentation/stores/__tests__/useJobFiltersStore.spec.ts src/modules/job-match/presentation/components/__tests__/JobFiltersBar.spec.ts`
Expected: FAIL, `store.setEmploymentType is not a function`

- [ ] **Step 4: Write minimal implementation**

In `useJobFiltersStore.ts`, add to the entity import: `PAY_FILTER_SITE`, `type JobPayType`.

Add after `isFiltered`:

```ts
  const showsPayFilters = computed(() => filters.value.site === PAY_FILTER_SITE)
```

Replace `setSite` and add the setters:

```ts
  function setSite(site: string | null): void {
    const pay = site === PAY_FILTER_SITE ? {} : { employmentType: null, salaryRange: null }
    filters.value = { ...filters.value, ...pay, site }
  }

  function setEmploymentType(employmentType: JobPayType | null): void {
    filters.value = { ...filters.value, employmentType, salaryRange: null }
  }

  function setSalaryRange(salaryRange: string | null): void {
    filters.value = { ...filters.value, salaryRange }
  }
```

Add `showsPayFilters`, `setEmploymentType`, and `setSalaryRange` to the returned object.

In `JobFiltersBar.vue`, add to the script imports:

```ts
import { SALARY_RANGES, type JobPayType } from '@/modules/job-match/domain/entities/JobFilters'
```

Add after `locationOptions`:

```ts
const typeLabelId = useId()
const typeTriggerId = useId()
const salaryLabelId = useId()
const salaryTriggerId = useId()

const employmentTypeOptions: SelectOption<JobPayType | null>[] = [
  { value: null, label: 'All job types' },
  { value: 'hourly', label: 'Hourly' },
  { value: 'fixed', label: 'Fixed' },
]
const salaryOptions = computed<SelectOption<string | null>[]>(() => {
  const employmentType = jobFilters.filters.employmentType
  const ranges = employmentType === null ? [] : SALARY_RANGES[employmentType]
  return [
    { value: null, label: 'All salaries' },
    ...ranges.map((range) => ({ value: range.value, label: range.label })),
  ]
})
```

Add to the template directly after the Location `AppSelect`:

```vue
    <template v-if="jobFilters.showsPayFilters">
      <span :id="typeLabelId" class="sr-only">Job type</span>
      <AppSelect
        :id="typeTriggerId"
        :aria-labelledby="`${typeLabelId} ${typeTriggerId}`"
        variant="pill"
        :model-value="jobFilters.filters.employmentType"
        :options="employmentTypeOptions"
        :disabled="disabled"
        @update:model-value="jobFilters.setEmploymentType"
      />
      <span :id="salaryLabelId" class="sr-only">Salary</span>
      <AppSelect
        :id="salaryTriggerId"
        :aria-labelledby="`${salaryLabelId} ${salaryTriggerId}`"
        variant="pill"
        :model-value="jobFilters.filters.salaryRange"
        :options="salaryOptions"
        :disabled="disabled || jobFilters.filters.employmentType === null"
        @update:model-value="jobFilters.setSalaryRange"
      />
    </template>
```

In `jobLabels.ts`, add to `SITE_LABELS`:

```ts
  upwork: 'Upwork',
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npx vitest run --exclude '.claude/**' src/modules/job-match/presentation/stores/__tests__/useJobFiltersStore.spec.ts src/modules/job-match/presentation/components/__tests__/JobFiltersBar.spec.ts`
Expected: PASS

- [ ] **Step 6: Run the frontend checks**

Run: `npx vue-tsc --noEmit && npx vitest run --exclude '.claude/**'`
Expected: PASS. Full-suite timeouts are a known flake: rerun any timed-out spec alone before calling it a failure.

- [ ] **Step 7: Check it in the real page**

Start the app, open Job Match, and confirm:
- Job type and Salary are hidden until Platform is Upwork.
- Salary is disabled until Hourly or Fixed is chosen.
- Ranges change with Job type.
- Picking a range changes the list and "load more" keeps the filter.
- Switching Platform away clears both.

## Handoff

Report these to the user:
- Mongo tests run or not run.
- Proxy path tested or not tested in Task 7.
- Real `contractorTier` values.
- Existing Mongo jobs from other sites have no `salary_min` or `salary_max`. They read as `None`.
