# API-First Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch JobStreet, Glints and LinkedIn jobs from each site's JSON/GraphQL/guest API first, and use the current HTML scrapers only as a fallback.

**Architecture:** A new `scraper/api/` package holds one HTTP client (curl_cffi session, pacing, typed errors) and one "API source" per site that maps API responses to our `Job` dict. The runner tries the API source first for each (site, keyword) pair. Any `ApiError` reruns that pair through the existing HTML path. Location and date go to the API as params; the existing Python max-age and location filters stay as a safety net. Each output payload records `source` (`api` or `html`) and `fallback_reason`, and the MCP server copies them into `run_metadata.per_site_sources`.

**Tech Stack:** Python 3.12+, curl_cffi (`impersonate="chrome131"`), pytest, PyYAML, existing MCP server (FastMCP) and MongoDB.

---

## Agreed design (from the grilling session)

| Topic | Decision |
|---|---|
| Scope | JobStreet + Glints move to their APIs. LinkedIn keeps its guest endpoint but gets per-city `location`, `f_TPR` from max age, and paging. Indeed already uses its GraphQL API and is **not** touched. JobSpy (`job-agent/JobSpy`) is reference only. |
| Fallback trigger | Only on API failure: HTTP error, non-JSON, GraphQL errors, network error. Zero results is a valid answer. |
| Fallback unit | Per site + keyword. One failed call reruns that whole site+keyword via HTML. |
| Detail fallback | Per job. Detail API first; on error or empty use the existing job-page fetch (`parse_detail`). |
| Filters | API params + existing Python filters as safety net. |
| Cities | One API call per city from a per-site `api.locations` list, plus one country-wide call that keeps only jobs labelled just `Indonesia`. Dedup by `job_id`, then URL. |
| Glints IDs | Static UUIDs in config. |
| `limit` | Still "max jobs after filters". Each API call pages up to `limit`. Dev limit goes from 2 to 30. |
| Date param | Derived from `max_age_hours`. |
| Tracking | `source` + `fallback_reason` in output payloads and `run_metadata.per_site_sources`. |
| Pacing | 1–2 s jittered delay between calls of one client; same proxy as fetchers. |
| Tests | TDD with inline JSON shaped like real responses. No live calls in CI. One manual smoke run. |
| Delivery | One branch, one commit per task. |

## Verified API facts (tested 2026-10-26 with curl_cffi, no browser cookies)

**JobStreet search** — `GET https://id.jobstreet.com/api/jobsearch/v5/search`
- Params: `siteKey=ID-Main`, `keywords`, `where` (e.g. `Jakarta Raya`), `daterange` (days), `page`, `pageSize` (≤100), `locale=id-ID`.
- Item fields used: `id`, `title`, `companyName`, `advertiser.description`, `locations[0].label`, `salaryLabel`, `listingDate` (`2026-10-26T07:34:52Z`), `listingDateDisplay`, `workTypes` (list of str, e.g. `["Contract/Temp"]`), `workArrangements` (`{"data":[{"label":{"text":"On-site"}}]}`).
- `where=Tangerang Banten` / `Bekasi Jawa Barat` also return Jakarta jobs (radius). Dedup handles the overlap.

**JobStreet detail** — `POST https://id.jobstreet.com/graphql`, headers `seek-request-brand: jobstreet`, `seek-request-country: ID`. Every declared GraphQL variable must be used, or the call fails with `GRAPHQL_VALIDATION_FAILED`.
```graphql
query jobDetails($jobId: ID!, $jobDetailsViewedCorrelationId: String!, $sessionId: String!) {
  jobDetails(id: $jobId, tracking: {channel: "WEB", jobDetailsViewedCorrelationId: $jobDetailsViewedCorrelationId, sessionId: $sessionId}) {
    job { content(platform: WEB) }
  }
}
```
`content` is HTML.

**Glints search** — `POST https://glints.com/api/v2-alc/graphql?op=searchJobsV3`
- Needs the `deviceid` cookie first: `GET https://glints.com/id/opportunities/jobs/explore?country=ID` on the same session. Without it the API ignores filters and returns 4 random jobs.
- Variables: `{"data": {"SearchTerm", "CountryCode": "ID", "LocationIds": [uuid], "page": 1, "pageSize": ≤50}}`.
- Anonymous limits: `pageSize` caps at 50; `page: 2` returns 403 `NO_PERMISSION`. So one call per city, max 50 jobs.
- Job URL `https://glints.com/id/opportunities/jobs/{id}` redirects to the slug URL (200).

**Glints detail** — same endpoint, `{ getJobById(id: "...") { descriptionJsonString } }` → Draft.js JSON (`{"blocks":[{"text","type"}]}`).

**Glints location UUIDs** (from `searchHierarchicalLocations` on `https://glints.com/api/graphql`):

| City | UUID | Level |
|---|---|---|
| DKI Jakarta (province) | `78d63064-78a1-4577-8516-036a6c5e903e` | 2 |
| Bandung | `86a3dc56-1bd7-4cd3-8225-d3e4b976e552` | 3 |
| Bekasi | `87c39cfb-0e3c-4edb-a7a0-754fb70cc587` | 3 |
| Tangerang | `ae3c458e-5947-4833-8f1b-e001ce2fad1d` | 3 |
| Tangerang Selatan | `337f8da8-70d8-4916-9733-1cee8e4902e9` | 3 |
| Indonesia (country) | `7542a4d7-4324-4f76-ae1f-2e37ffb1198b` | 1 |

**LinkedIn guest** — `GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords&location&f_TPR=r<seconds>&start`. Returns HTML `<li>` cards, 10 per page, parsed by the existing `LinkedinScraper.parse`. Returns `429` quickly when called back to back. There is no JSON or detail API, so LinkedIn detail stays on the job-page fetch.

## File structure

| File | Responsibility |
|---|---|
| Create `scraper/api/__init__.py` | Public exports. |
| Create `scraper/api/client.py` | `ApiClient` (session, pacing, GET/POST, JSON), `ApiError`, `graphql_data`. |
| Create `scraper/api/window.py` | `days_window`, `seconds_window`, `to_utc_iso`. |
| Create `scraper/api/draftjs.py` | `draftjs_to_markdown`. |
| Create `scraper/api/source.py` | `ApiSource` protocol, `search_all`, `dedup_jobs`, `is_country_level`. |
| Create `scraper/api/jobstreet.py` | `JobstreetApi`. |
| Create `scraper/api/glints.py` | `GlintsApi`. |
| Create `scraper/api/linkedin.py` | `LinkedinApi`. |
| Create `scraper/api/registry.py` | `API_SOURCES` map. |
| Modify `scraper/config_loader.py` | `ApiConfig`, `SiteConfig.api`, `_parse_api`. |
| Modify `scraper/runner.py` | API-first + fallback, `source`/`fallback_reason` in payloads, detail callback. |
| Modify `mcp_server/server.py` | `_build_per_site_sources` → `run_metadata.per_site_sources`. |
| Modify `config.yaml`, `config.dev.patch.yaml` | `api:` blocks; dev limit 30. |
| Modify `docs/configuration.md`, `docs/sites.md` | Document `api:` block and fallback. |
| Tests | `tests/api_fakes.py`, `tests/test_api_client.py`, `tests/test_api_window.py`, `tests/test_api_draftjs.py`, `tests/test_api_source.py`, `tests/test_api_jobstreet.py`, `tests/test_api_glints.py`, `tests/test_api_linkedin.py`, `tests/test_config_api.py`, `tests/test_runner_api.py`, `tests/test_server_sources.py`. |

All commands run from `job-agent/scraper/` with `.venv/bin/python`.

---

### Task 0: Branch

- [ ] **Step 1: Check the tree**

Run: `git status -sb`
Expected: the current branch is `feat/markdown-requirements` with uncommitted edits to `.github/workflows/deploy.yml`, `config.dev.patch.yaml`, `docker-compose.yml`, `requirements.txt`. These are not part of this plan. Ask the user whether to commit, stash, or keep them before branching. Do not discard them.

- [ ] **Step 2: Create the branch**

```bash
git switch -c feat/api-first-scraper
```

- [ ] **Step 3: Baseline**

Run: `.venv/bin/python -m pytest -q`
Expected: `112 passed`.

---

### Task 1: `ApiClient`, `ApiError`, `graphql_data`

**Files:**
- Create: `scraper/api/__init__.py`, `scraper/api/client.py`
- Create: `tests/api_fakes.py`
- Test: `tests/test_api_client.py`

- [ ] **Step 1: Write the test fakes**

`tests/api_fakes.py`:
```python
from __future__ import annotations

from typing import Any

from scraper.api.client import ApiClient


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_client(responses: list[FakeResponse | Exception]) -> tuple[ApiClient, FakeSession]:
    session = FakeSession(responses)
    client = ApiClient(session_factory=lambda: session, sleep=lambda _s: None)
    return client, session
```

- [ ] **Step 2: Write the failing tests**

`tests/test_api_client.py`:
```python
from __future__ import annotations

import pytest

from scraper.api.client import ApiClient, ApiError, graphql_data
from tests.api_fakes import FakeResponse, FakeSession, make_client


def test_get_json_returns_payload_and_passes_params():
    client, session = make_client([FakeResponse(payload={"data": [1]})])
    assert client.get_json("https://x.test/a", params={"q": "devops"}) == {"data": [1]}
    method, url, kwargs = session.calls[0]
    assert (method, url, kwargs["params"]) == ("GET", "https://x.test/a", {"q": "devops"})


def test_post_json_sends_body_and_headers():
    client, session = make_client([FakeResponse(payload={"ok": True})])
    client.post_json("https://x.test/g", {"query": "q"}, headers={"h": "1"})
    _, _, kwargs = session.calls[0]
    assert kwargs["json"] == {"query": "q"}
    assert kwargs["headers"] == {"h": "1"}


def test_non_200_raises_http_code():
    client, _ = make_client([FakeResponse(status_code=429, text="slow down")])
    with pytest.raises(ApiError) as err:
        client.get_json("https://x.test/a")
    assert err.value.code == "http_429"


def test_network_exception_raises_runtime_error():
    client, _ = make_client([ConnectionError("boom")])
    with pytest.raises(ApiError) as err:
        client.get_text("https://x.test/a")
    assert err.value.code == "runtime_error"


def test_non_json_raises():
    client, _ = make_client([FakeResponse(payload=None, text="<html>")])
    with pytest.raises(ApiError) as err:
        client.get_json("https://x.test/a")
    assert err.value.code == "non_json"


def test_non_object_json_raises():
    client, _ = make_client([FakeResponse(payload=[1, 2])])
    with pytest.raises(ApiError) as err:
        client.get_json("https://x.test/a")
    assert err.value.code == "non_json"


def test_pacing_sleeps_between_calls_not_before_first():
    session = FakeSession([FakeResponse(payload={}), FakeResponse(payload={})])
    sleeps: list[float] = []
    client = ApiClient(
        session_factory=lambda: session,
        sleep=sleeps.append,
        rand=lambda low, high: (low + high) / 2,
    )
    client.get_json("https://x.test/1")
    client.get_json("https://x.test/2")
    assert sleeps == [1.5]


def test_warm_does_a_get():
    client, session = make_client([FakeResponse(text="<html>")])
    client.warm("https://x.test/page")
    assert session.calls[0][0:2] == ("GET", "https://x.test/page")


def test_graphql_data_returns_field():
    assert graphql_data({"data": {"search": [1]}}, "search") == [1]


def test_graphql_data_raises_on_errors():
    with pytest.raises(ApiError) as err:
        graphql_data({"data": None, "errors": [{"message": "NO_PERMISSION"}]}, "search")
    assert err.value.code == "graphql_error"


def test_graphql_data_raises_on_missing_field():
    with pytest.raises(ApiError) as err:
        graphql_data({"data": {}}, "search")
    assert err.value.code == "graphql_error"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api_client.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.api'`.

- [ ] **Step 4: Implement**

`scraper/api/__init__.py`:
```python
from __future__ import annotations

from .client import ApiClient, ApiError

__all__ = ["ApiClient", "ApiError"]
```

`scraper/api/client.py`:
```python
from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any

_IMPERSONATE = "chrome131"
_TIMEOUT_SECONDS = 30
_ERROR_BODY_CHARS = 200
DEFAULT_DELAY_SECONDS: tuple[float, float] = (1.0, 2.0)


class ApiError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class ApiClient:
    """One curl_cffi session per (site, keyword) run, with jittered pacing between calls."""

    def __init__(
        self,
        proxy: str | None = None,
        delay: tuple[float, float] = DEFAULT_DELAY_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        rand: Callable[[float, float], float] = random.uniform,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._proxy = proxy
        self._delay = delay
        self._sleep = sleep
        self._rand = rand
        self._session_factory = session_factory or self._default_session
        self._session: Any = None
        self._has_requested = False

    def _default_session(self) -> Any:
        from curl_cffi import requests as cffi_requests  # type: ignore[attr-defined]

        proxies = {"http": self._proxy, "https": self._proxy} if self._proxy else None
        return cffi_requests.Session(impersonate=_IMPERSONATE, proxies=proxies)

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        if self._session is None:
            self._session = self._session_factory()
        if self._has_requested:
            self._sleep(self._rand(*self._delay))
        self._has_requested = True
        try:
            response = self._session.request(method, url, timeout=_TIMEOUT_SECONDS, **kwargs)
        except Exception as exc:
            raise ApiError("runtime_error", f"{type(exc).__name__}: {exc}") from exc
        if response.status_code != 200:
            raise ApiError(f"http_{response.status_code}", response.text[:_ERROR_BODY_CHARS])
        return response

    def warm(self, url: str) -> None:
        self._request("GET", url)

    def get_text(
        self, url: str, params: dict[str, str] | None = None, headers: dict[str, str] | None = None
    ) -> str:
        return self._request("GET", url, params=params, headers=headers).text

    def get_json(
        self, url: str, params: dict[str, str] | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        return _json_object(self._request("GET", url, params=params, headers=headers))

    def post_json(
        self, url: str, body: dict[str, Any], headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        return _json_object(self._request("POST", url, json=body, headers=headers))


def _json_object(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ApiError("non_json", str(exc)) from exc
    if not isinstance(payload, dict):
        raise ApiError("non_json", "top-level JSON is not an object")
    return payload


def graphql_data(payload: dict[str, Any], field: str) -> Any:
    errors = payload.get("errors")
    if errors:
        raise ApiError("graphql_error", str(errors)[:_ERROR_BODY_CHARS])
    data = (payload.get("data") or {}).get(field)
    if data is None:
        raise ApiError("graphql_error", f"missing data.{field}")
    return data
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api_client.py -q`
Expected: `11 passed`.

- [ ] **Step 6: Commit**

```bash
git add scraper/api/__init__.py scraper/api/client.py tests/api_fakes.py tests/test_api_client.py
git commit -m "feat: add paced API client with typed errors"
```

---

### Task 2: Date window and Draft.js helpers

**Files:**
- Create: `scraper/api/window.py`, `scraper/api/draftjs.py`
- Test: `tests/test_api_window.py`, `tests/test_api_draftjs.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_api_window.py`:
```python
from __future__ import annotations

from scraper.api.window import days_window, seconds_window, to_utc_iso


def test_days_window_rounds_up_and_floors_at_one():
    assert days_window(72) == 3
    assert days_window(73) == 4
    assert days_window(1) == 1


def test_windows_are_none_without_max_age():
    assert days_window(None) is None
    assert seconds_window(None) is None


def test_seconds_window():
    assert seconds_window(72) == 259200


def test_to_utc_iso_normalizes_z_suffix():
    assert to_utc_iso("2026-10-26T07:34:52Z") == "2026-10-26T07:34:52+00:00"


def test_to_utc_iso_rejects_garbage():
    assert to_utc_iso("6h ago") is None
    assert to_utc_iso(None) is None
```

`tests/test_api_draftjs.py`:
```python
from __future__ import annotations

import json

from scraper.api.draftjs import draftjs_to_markdown


def _raw(*blocks: tuple[str, str]) -> str:
    return json.dumps({"blocks": [{"text": text, "type": kind} for text, kind in blocks]})


def test_paragraphs_and_lists():
    raw = _raw(
        ("Requirements", "header-three"),
        ("AWS experience", "unordered-list-item"),
        ("Terraform", "unordered-list-item"),
        ("Step one", "ordered-list-item"),
        ("Nice to have.", "unstyled"),
    )
    assert draftjs_to_markdown(raw) == (
        "### Requirements\n- AWS experience\n- Terraform\n1. Step one\nNice to have."
    )


def test_blank_blocks_are_skipped():
    assert draftjs_to_markdown(_raw(("", "unstyled"), ("Only", "unstyled"))) == "Only"


def test_invalid_input_returns_none():
    assert draftjs_to_markdown(None) is None
    assert draftjs_to_markdown("not json") is None
    assert draftjs_to_markdown(json.dumps({"blocks": []})) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api_window.py tests/test_api_draftjs.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`scraper/api/window.py`:
```python
from __future__ import annotations

import math
from datetime import UTC, datetime

_HOURS_PER_DAY = 24
_SECONDS_PER_HOUR = 3600


def days_window(max_age_hours: int | None) -> int | None:
    if max_age_hours is None:
        return None
    return max(1, math.ceil(max_age_hours / _HOURS_PER_DAY))


def seconds_window(max_age_hours: int | None) -> int | None:
    if max_age_hours is None:
        return None
    return max_age_hours * _SECONDS_PER_HOUR


def to_utc_iso(raw: str | None) -> str | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()
```

`scraper/api/draftjs.py`:
```python
from __future__ import annotations

import json

_PREFIX_BY_TYPE = {
    "unordered-list-item": "- ",
    "ordered-list-item": "1. ",
    "header-one": "# ",
    "header-two": "## ",
    "header-three": "### ",
}


def draftjs_to_markdown(raw: str | None) -> str | None:
    """Glints stores descriptions as Draft.js JSON: {"blocks": [{"text", "type"}]}."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    blocks = payload.get("blocks") if isinstance(payload, dict) else None
    if not isinstance(blocks, list):
        return None
    lines = [
        _PREFIX_BY_TYPE.get(str(block.get("type")), "") + block["text"].strip()
        for block in blocks
        if isinstance(block, dict) and isinstance(block.get("text"), str) and block["text"].strip()
    ]
    return "\n".join(lines) or None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api_window.py tests/test_api_draftjs.py -q`
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add scraper/api/window.py scraper/api/draftjs.py tests/test_api_window.py tests/test_api_draftjs.py
git commit -m "feat: add date-window and Draft.js helpers for API sources"
```

---

### Task 3: `ApiSource` protocol, per-city search, dedup

**Files:**
- Create: `scraper/api/source.py`
- Test: `tests/test_api_source.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_api_source.py`:
```python
from __future__ import annotations

import pytest

from scraper.api.client import ApiError
from scraper.api.source import dedup_jobs, is_country_level, search_all
from scraper.types import Job, empty_job


def _job(job_id: str | None, location: str, url: str | None = None) -> Job:
    job = empty_job("jobstreet", f"T{job_id}", "C")
    job["job_id"] = job_id
    job["url"] = url
    job["location"] = location
    return job


class StubSource:
    name = "stub"
    country_location = "COUNTRY"

    def __init__(self, by_location: dict[str | None, list[Job] | Exception]) -> None:
        self.by_location = by_location
        self.calls: list[tuple[str, str | None, int | None, int]] = []

    def search(self, keyword: str, location: str | None, max_age_hours: int | None, limit: int):
        self.calls.append((keyword, location, max_age_hours, limit))
        result = self.by_location[location]
        if isinstance(result, Exception):
            raise result
        return list(result)

    def detail(self, job: Job) -> str | None:
        return None


def test_one_call_per_city_then_dedup():
    source = StubSource({"A": [_job("1", "Jakarta"), _job("2", "Jakarta")], "B": [_job("2", "Jakarta")]})
    jobs = search_all(source, "devops", ("A", "B"), country_wide=False, max_age_hours=72, limit=30)
    assert [j["job_id"] for j in jobs] == ["1", "2"]
    assert source.calls == [("devops", "A", 72, 30), ("devops", "B", 72, 30)]


def test_country_call_keeps_only_country_level_jobs():
    source = StubSource({"A": [_job("1", "Jakarta")], "COUNTRY": [_job("9", "Indonesia"), _job("8", "Bali")]})
    jobs = search_all(source, "devops", ("A",), country_wide=True, max_age_hours=None, limit=30)
    assert [j["job_id"] for j in jobs] == ["1", "9"]


def test_api_error_propagates_for_site_level_fallback():
    source = StubSource({"A": [_job("1", "Jakarta")], "B": ApiError("http_500")})
    with pytest.raises(ApiError):
        search_all(source, "devops", ("A", "B"), country_wide=False, max_age_hours=None, limit=30)


def test_dedup_falls_back_to_url_then_title_company():
    a = _job(None, "Jakarta", url="https://x/1")
    b = _job(None, "Jakarta", url="https://x/1")
    c = _job(None, "Jakarta")
    d = _job(None, "Jakarta")
    assert dedup_jobs([a, b, c, d]) == [a, c]


def test_is_country_level():
    assert is_country_level(_job("1", " Indonesia "))
    assert not is_country_level(_job("1", "Jakarta, Indonesia"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api_source.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`scraper/api/source.py`:
```python
from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from ..types import Job

COUNTRY_LABELS: frozenset[str] = frozenset({"indonesia"})


class ApiSource(Protocol):
    name: str
    # value passed as `location` for the country-wide call (None = no location param)
    country_location: str | None

    def search(
        self, keyword: str, location: str | None, max_age_hours: int | None, limit: int
    ) -> list[Job]: ...

    def detail(self, job: Job) -> str | None: ...


def is_country_level(job: Job) -> bool:
    return (job.get("location") or "").strip().lower() in COUNTRY_LABELS


def _dedup_key(job: Job) -> tuple[str, ...]:
    if job.get("job_id"):
        return ("id", str(job["job_id"]))
    if job.get("url"):
        return ("url", str(job["url"]))
    return ("tc", job["title"], job["company"])


def dedup_jobs(jobs: Iterable[Job]) -> list[Job]:
    seen: set[tuple[str, ...]] = set()
    unique: list[Job] = []
    for job in jobs:
        key = _dedup_key(job)
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique


def search_all(
    source: ApiSource,
    keyword: str,
    locations: Iterable[str],
    country_wide: bool,
    max_age_hours: int | None,
    limit: int,
) -> list[Job]:
    """One call per city, plus an optional country-wide call kept to 'Indonesia'-only jobs.

    ApiError is not caught: the runner falls back to HTML for the whole site+keyword.
    """
    jobs: list[Job] = []
    for location in locations:
        jobs.extend(source.search(keyword, location, max_age_hours, limit))
    if country_wide:
        country_jobs = source.search(keyword, source.country_location, max_age_hours, limit)
        jobs.extend(job for job in country_jobs if is_country_level(job))
    return dedup_jobs(jobs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api_source.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add scraper/api/source.py tests/test_api_source.py
git commit -m "feat: add per-city API search with dedup"
```

---

### Task 4: `JobstreetApi`

**Files:**
- Create: `scraper/api/jobstreet.py`
- Test: `tests/test_api_jobstreet.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_api_jobstreet.py`:
```python
from __future__ import annotations

import pytest

from scraper.api.client import ApiError
from scraper.api.jobstreet import JobstreetApi
from scraper.types import empty_job
from tests.api_fakes import FakeResponse, make_client


def _item(job_id: str, **overrides):
    item = {
        "id": job_id,
        "title": "Devops",
        "companyName": "Platinumetrix Global Innovations",
        "advertiser": {"id": "61020132", "description": "PT Platinumetrix Global Inovasi"},
        "locations": [{"label": "Jakarta", "countryCode": "ID"}],
        "salaryLabel": "Rp 9.000.000 – Rp 12.000.000 per month",
        "listingDate": "2026-10-26T07:34:52Z",
        "listingDateDisplay": "6h ago",
        "workTypes": ["Contract/Temp"],
        "workArrangements": {"data": [{"id": "1", "label": {"text": "On-site"}}]},
    }
    item.update(overrides)
    return item


def test_search_maps_fields_and_sends_params():
    client, session = make_client([FakeResponse(payload={"data": [_item("95497990")], "totalCount": 1})])
    jobs = JobstreetApi(client).search("devops", "Jakarta Raya", 72, 30)

    params = session.calls[0][2]["params"]
    assert params["siteKey"] == "ID-Main"
    assert params["keywords"] == "devops"
    assert params["where"] == "Jakarta Raya"
    assert params["daterange"] == "3"
    assert params["pageSize"] == "30"
    assert params["page"] == "1"

    job = jobs[0]
    assert job["site"] == "jobstreet"
    assert job["company"] == "PT Platinumetrix Global Inovasi"
    assert job["job_id"] == "95497990"
    assert job["url"] == "https://id.jobstreet.com/id/job/95497990"
    assert job["location"] == "Jakarta"
    assert job["posted_at"] == "2026-10-26T07:34:52+00:00"
    assert job["posted_date"] == "6h ago"
    assert job["employment_type"] == "contract/temp"
    assert job["work_type"] == "on-site"
    assert job["requirements"] is None


def test_country_call_omits_where_and_no_age_omits_daterange():
    client, session = make_client([FakeResponse(payload={"data": []})])
    JobstreetApi(client).search("devops", None, None, 30)
    params = session.calls[0][2]["params"]
    assert "where" not in params
    assert "daterange" not in params


def test_pages_until_limit():
    page1 = {"data": [_item(str(i)) for i in range(100)]}
    page2 = {"data": [_item(str(i)) for i in range(100, 150)]}
    client, session = make_client([FakeResponse(payload=page1), FakeResponse(payload=page2)])
    jobs = JobstreetApi(client).search("devops", "Jakarta Raya", 72, 150)
    assert len(jobs) == 150
    assert [c[2]["params"]["page"] for c in session.calls] == ["1", "2"]


def test_stops_on_short_page():
    client, session = make_client([FakeResponse(payload={"data": [_item("1")]})])
    assert len(JobstreetApi(client).search("devops", "Jakarta Raya", 72, 150)) == 1
    assert len(session.calls) == 1


def test_skips_items_without_title_or_company():
    bad = _item("2", title=None)
    client, _ = make_client([FakeResponse(payload={"data": [bad, _item("1")]})])
    assert [j["job_id"] for j in JobstreetApi(client).search("devops", None, None, 30)] == ["1"]


def test_missing_data_list_is_an_error():
    client, _ = make_client([FakeResponse(payload={"error": "nope"})])
    with pytest.raises(ApiError):
        JobstreetApi(client).search("devops", None, None, 30)


def test_detail_returns_markdown_from_graphql():
    payload = {"data": {"jobDetails": {"job": {"content": "<p>Pengalaman Devops</p>"}}}}
    client, session = make_client([FakeResponse(payload=payload)])
    job = empty_job("jobstreet", "Devops", "PT X")
    job["job_id"] = "95497990"
    assert JobstreetApi(client).detail(job) == "Pengalaman Devops"
    method, url, kwargs = session.calls[0]
    assert (method, url) == ("POST", "https://id.jobstreet.com/graphql")
    assert kwargs["json"]["variables"]["jobId"] == "95497990"
    assert kwargs["headers"]["seek-request-country"] == "ID"


def test_detail_without_job_id_returns_none():
    client, session = make_client([])
    assert JobstreetApi(client).detail(empty_job("jobstreet", "T", "C")) is None
    assert session.calls == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api_jobstreet.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`scraper/api/jobstreet.py`:
```python
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
            "keywords": keyword,
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api_jobstreet.py -q`
Expected: `8 passed`. If `test_detail_returns_markdown_from_graphql` fails on exact text, print `html_to_markdown("<p>Pengalaman Devops</p>")` and match the assertion to its real output (it strips tags; the helper is shared with the HTML scrapers and must not change).

- [ ] **Step 5: Commit**

```bash
git add scraper/api/jobstreet.py tests/test_api_jobstreet.py
git commit -m "feat: add JobStreet v5 search and GraphQL detail API source"
```

---

### Task 5: `GlintsApi`

**Files:**
- Create: `scraper/api/glints.py`
- Test: `tests/test_api_glints.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_api_glints.py`:
```python
from __future__ import annotations

import json

import pytest

from scraper.api.client import ApiError
from scraper.api.glints import COUNTRY_ID, GlintsApi
from scraper.types import empty_job
from tests.api_fakes import FakeResponse, make_client

JAKARTA = "78d63064-78a1-4577-8516-036a6c5e903e"


def _item(job_id: str, **overrides):
    item = {
        "id": job_id,
        "title": "Sr. DevOps",
        "createdAt": "2026-10-26T09:25:59.250383Z",
        "type": "FULL_TIME",
        "workArrangementOption": "HYBRID",
        "minYearsOfExperience": 3,
        "maxYearsOfExperience": 5,
        "company": {"name": "Insignia"},
        "location": {
            "formattedName": "Kebon Jeruk",
            "parents": [
                {"formattedName": "Indonesia", "level": 1},
                {"formattedName": "DKI Jakarta", "level": 2},
                {"formattedName": "Jakarta Barat", "level": 3},
            ],
        },
        "salaries": [
            {"CurrencyCode": "IDR", "minAmount": 14000000, "maxAmount": 15000000, "salaryMode": "MONTH"}
        ],
    }
    item.update(overrides)
    return item


def _search(items):
    return FakeResponse(payload={"data": {"searchJobsV3": {"hasMore": False, "jobsInPage": items}}})


def test_warms_once_then_searches_with_location_ids():
    client, session = make_client([FakeResponse(text="<html>"), _search([_item("a")]), _search([])])
    api = GlintsApi(client)
    api.search("devops", JAKARTA, 72, 30)
    api.search("devops", JAKARTA, 72, 30)

    assert session.calls[0][0] == "GET"
    assert [c[0] for c in session.calls[1:]] == ["POST", "POST"]
    data = session.calls[1][2]["json"]["variables"]["data"]
    assert data == {
        "SearchTerm": "devops",
        "CountryCode": "ID",
        "LocationIds": [JAKARTA],
        "page": 1,
        "pageSize": 30,
    }


def test_page_size_caps_at_50():
    client, session = make_client([FakeResponse(text=""), _search([])])
    GlintsApi(client).search("devops", JAKARTA, None, 200)
    assert session.calls[1][2]["json"]["variables"]["data"]["pageSize"] == 50


def test_maps_fields():
    client, _ = make_client([FakeResponse(text=""), _search([_item("ead43098")])])
    job = GlintsApi(client).search("devops", JAKARTA, 72, 30)[0]
    assert job["site"] == "glints"
    assert job["company"] == "Insignia"
    assert job["job_id"] == "ead43098"
    assert job["url"] == "https://glints.com/id/opportunities/jobs/ead43098"
    assert job["location"] == "Kebon Jeruk, Jakarta Barat, DKI Jakarta"
    assert job["posted_at"] == "2026-10-26T09:25:59.250383+00:00"
    assert job["salary"] == "IDR 14,000,000 - 15,000,000 per month"
    assert job["employment_type"] == "full_time"
    assert job["work_type"] == "hybrid"
    assert job["experience_level"] == "3-5 years"


def test_country_level_job_location_is_country_name():
    item = _item("x", location={"formattedName": "Indonesia", "parents": []})
    client, _ = make_client([FakeResponse(text=""), _search([item])])
    assert GlintsApi(client).search("devops", COUNTRY_ID, None, 30)[0]["location"] == "Indonesia"


def test_no_salary_and_min_only_experience():
    item = _item("x", salaries=None, maxYearsOfExperience=None)
    client, _ = make_client([FakeResponse(text=""), _search([item])])
    job = GlintsApi(client).search("devops", JAKARTA, None, 30)[0]
    assert job["salary"] is None
    assert job["experience_level"] == "3+ years"


def test_graphql_error_raises():
    error = FakeResponse(payload={"data": None, "errors": [{"message": "please login"}]})
    client, _ = make_client([FakeResponse(text=""), error])
    with pytest.raises(ApiError):
        GlintsApi(client).search("devops", JAKARTA, None, 30)


def test_detail_converts_draftjs():
    raw = json.dumps({"blocks": [{"text": "AWS", "type": "unordered-list-item"}]})
    detail = FakeResponse(payload={"data": {"getJobById": {"descriptionJsonString": raw}}})
    client, session = make_client([FakeResponse(text=""), detail])
    job = empty_job("glints", "T", "C")
    job["job_id"] = "ead43098"
    assert GlintsApi(client).detail(job) == "- AWS"
    assert session.calls[1][2]["json"]["variables"] == {"id": "ead43098"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api_glints.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`scraper/api/glints.py`:
```python
from __future__ import annotations

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
    company = (item.get("company") or {}).get("name") if isinstance(item.get("company"), dict) else None
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

    def _post(self, operation: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        if not self._is_warm:
            self._client.warm(WARM_URL)
            self._is_warm = True
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
        result = graphql_data(self._post("searchJobsV3", SEARCH_QUERY, {"data": data}), "searchJobsV3")
        items = result.get("jobsInPage") or []
        return [job for item in items if isinstance(item, dict) and (job := _to_job(item))]

    def detail(self, job: Job) -> str | None:
        job_id = job.get("job_id")
        if not job_id:
            return None
        found = graphql_data(self._post("getJobById", DETAIL_QUERY, {"id": job_id}), "getJobById")
        return draftjs_to_markdown(found.get("descriptionJsonString"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api_glints.py -q`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add scraper/api/glints.py tests/test_api_glints.py
git commit -m "feat: add Glints searchJobsV3 and getJobById API source"
```

---

### Task 6: `LinkedinApi`

**Files:**
- Create: `scraper/api/linkedin.py`
- Test: `tests/test_api_linkedin.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_api_linkedin.py`:
```python
from __future__ import annotations

import pytest

from scraper.api.client import ApiError
from scraper.api.linkedin import LinkedinApi
from scraper.types import empty_job
from tests.api_fakes import FakeResponse, make_client


def _card(job_id: int, location: str = "Jakarta, Indonesia") -> str:
    return (
        "<li><div class='base-search-card'>"
        f"<a class='base-card__full-link' href='https://id.linkedin.com/jobs/view/devops-{job_id}?trk=x'></a>"
        f"<h3 class='base-search-card__title'>DevOps {job_id}</h3>"
        "<h4 class='base-search-card__subtitle'><a>Acme</a></h4>"
        f"<span class='job-search-card__location'>{location}</span>"
        "<time class='job-search-card__listdate' datetime='2026-10-25'>1 day ago</time>"
        "</div></li>"
    )


def _page(start: int, count: int) -> FakeResponse:
    return FakeResponse(text="".join(_card(i) for i in range(start, start + count)))


def test_sends_location_tpr_and_start():
    client, session = make_client([_page(0, 3)])
    jobs = LinkedinApi(client).search("devops", "Jakarta, Indonesia", 72, 30)
    params = session.calls[0][2]["params"]
    assert params == {
        "keywords": "devops",
        "location": "Jakarta, Indonesia",
        "f_TPR": "r259200",
        "start": "0",
    }
    assert len(jobs) == 3
    assert jobs[0]["site"] == "linkedin"
    assert jobs[0]["location"] == "Jakarta, Indonesia"


def test_pages_by_ten_until_limit():
    client, session = make_client([_page(0, 10), _page(10, 10), _page(20, 10)])
    jobs = LinkedinApi(client).search("devops", "Jakarta, Indonesia", None, 25)
    assert len(jobs) == 25
    assert [c[2]["params"]["start"] for c in session.calls] == ["0", "10", "20"]
    assert "f_TPR" not in session.calls[0][2]["params"]


def test_stops_on_empty_page():
    client, session = make_client([_page(0, 10), FakeResponse(text="")])
    assert len(LinkedinApi(client).search("devops", "Indonesia", None, 50)) == 10
    assert len(session.calls) == 2


def test_rate_limit_raises_for_fallback():
    client, _ = make_client([FakeResponse(status_code=429)])
    with pytest.raises(ApiError):
        LinkedinApi(client).search("devops", "Indonesia", None, 10)


def test_detail_is_none_so_runner_uses_job_page():
    client, _ = make_client([])
    assert LinkedinApi(client).detail(empty_job("linkedin", "T", "C")) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api_linkedin.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`scraper/api/linkedin.py`:
```python
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
            if len(jobs) >= limit:
                break
        return jobs[:limit]

    def detail(self, job: Job) -> str | None:
        return None  # no detail API; the runner fetches the job page
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api_linkedin.py -q`
Expected: `5 passed`. If `test_sends_location_tpr_and_start` fails on dict order or `location` text, compare with `LinkedinScraper.parse` output on `_card(1)` and fix the test fixture, not the parser.

- [ ] **Step 5: Commit**

```bash
git add scraper/api/linkedin.py tests/test_api_linkedin.py
git commit -m "feat: add LinkedIn guest API source with per-city paging"
```

---

### Task 7: Registry and config `api:` block

**Files:**
- Create: `scraper/api/registry.py`
- Modify: `scraper/config_loader.py` (add `ApiConfig`; `SiteConfig.api`; parse in `load`)
- Test: `tests/test_config_api.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_config_api.py`:
```python
from __future__ import annotations

from pathlib import Path

import pytest

from scraper.api.registry import API_SOURCES
from scraper.config_loader import ApiConfig, ConfigError, load

BASE = """
keywords: [devops]
sites:
  jobstreet:
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs"
"""


def _write(tmp_path: Path, extra: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(BASE + extra)
    return path


def test_api_block_parsed(tmp_path: Path):
    path = _write(
        tmp_path,
        """    api:
      enabled: true
      locations: [Jakarta Raya, Bandung Jawa Barat]
      country_wide: true
""",
    )
    site = load(path).site("jobstreet")
    assert site is not None
    assert site.api == ApiConfig(
        enabled=True, locations=("Jakarta Raya", "Bandung Jawa Barat"), country_wide=True
    )


def test_missing_api_block_is_none(tmp_path: Path):
    site = load(_write(tmp_path, "")).site("jobstreet")
    assert site is not None
    assert site.api is None


def test_api_defaults(tmp_path: Path):
    site = load(_write(tmp_path, "    api: {}\n")).site("jobstreet")
    assert site is not None
    assert site.api == ApiConfig(enabled=True, locations=(), country_wide=False)


def test_locations_must_be_list_of_strings(tmp_path: Path):
    with pytest.raises(ConfigError, match="sites.jobstreet.api.locations"):
        load(_write(tmp_path, "    api:\n      locations: Jakarta\n"))


def test_registry_has_api_sites():
    assert set(API_SOURCES) == {"jobstreet", "glints", "linkedin"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config_api.py -q`
Expected: FAIL with `ImportError: cannot import name 'ApiConfig'` or `ModuleNotFoundError: scraper.api.registry`.

- [ ] **Step 3: Implement the registry**

`scraper/api/registry.py`:
```python
from __future__ import annotations

from collections.abc import Callable

from .client import ApiClient
from .glints import GlintsApi
from .jobstreet import JobstreetApi
from .linkedin import LinkedinApi
from .source import ApiSource

API_SOURCES: dict[str, Callable[[ApiClient], ApiSource]] = {
    "jobstreet": JobstreetApi,
    "glints": GlintsApi,
    "linkedin": LinkedinApi,
}
```

- [ ] **Step 4: Add `ApiConfig` to `scraper/config_loader.py`**

Add this dataclass right above `class SiteConfig`:
```python
@dataclass(frozen=True)
class ApiConfig:
    enabled: bool
    locations: tuple[str, ...]
    country_wide: bool
```

Add the field as the last field of `SiteConfig` (after `limit: int | None = None`):
```python
    api: ApiConfig | None = None
```

Add this parser function directly above `def load(path: Path) -> AppConfig:`:
```python
def _parse_api(raw: object, source: str) -> ApiConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigError(f"{source} must be a mapping")
    locations_raw = raw.get("locations", [])
    if not isinstance(locations_raw, list) or not all(
        isinstance(item, str) and item.strip() for item in locations_raw
    ):
        raise ConfigError(f"{source}.locations must be a list of non-empty strings")
    return ApiConfig(
        enabled=bool(raw.get("enabled", True)),
        locations=tuple(item.strip() for item in locations_raw),
        country_wide=bool(raw.get("country_wide", False)),
    )
```

In `load`, inside the `for name, cfg in sites_raw.items():` loop, pass the parsed block to `SiteConfig(...)` by adding this keyword argument after `limit=site_limit,`:
```python
                api=_parse_api(cfg.get("api"), f"sites.{name}.api"),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config_api.py -q`
Expected: `5 passed`.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass (112 old + new).

- [ ] **Step 7: Commit**

```bash
git add scraper/api/registry.py scraper/config_loader.py tests/test_config_api.py
git commit -m "feat: add per-site api config block and API source registry"
```

---

### Task 8: Runner — API first, HTML fallback, source tracking, detail callback

**Files:**
- Modify: `scraper/runner.py` (`_fetch_requirements`, `run_one`, `run._process`)
- Test: `tests/test_runner_api.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_runner_api.py`:
```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from scraper.api.client import ApiError
from scraper.runner import run_one
from scraper.sites.linkedin import LinkedinScraper
from scraper.types import empty_job

FIELDS = frozenset({"site", "matched_keyword", "title", "company", "url", "location", "requirements"})


def _fetcher(html: str | None):
    fetcher = MagicMock()
    result = MagicMock()
    result.html = html
    result.attempts = ()
    fetcher.fetch.return_value = result
    return fetcher


def _api_job(job_id: str):
    job = empty_job("linkedin", f"Role {job_id}", "Acme")
    job["job_id"] = job_id
    job["url"] = f"https://www.linkedin.com/jobs/view/{job_id}"
    job["location"] = "Jakarta"
    return job


HTML_CARD = (
    "<li><h3 class='base-search-card__title'>Html Role</h3>"
    "<h4 class='base-search-card__subtitle'><a>Acme</a></h4>"
    "<span class='job-search-card__location'>Jakarta</span>"
    "<a class='base-card__full-link' href='https://www.linkedin.com/jobs/view/777'></a></li>"
)


def _scraper():
    return LinkedinScraper(url="https://www.linkedin.com/jobs-guest/x", limit=10)


def _read(tmp_path: Path, name: str) -> dict:
    return json.loads((tmp_path / name).read_text())


def test_api_success_skips_html_fetch_and_records_source(tmp_path: Path):
    fetcher = _fetcher(HTML_CARD)
    run_one(
        _scraper(), fetcher, tmp_path, "devops", FIELDS - {"requirements"}, None, {},
        api_search=lambda: [_api_job("1"), _api_job("2")],
    )
    out = _read(tmp_path, "linkedin.json")
    raw = _read(tmp_path, "linkedin.raw.json")
    assert out["count"] == 2
    assert out["source"] == "api"
    assert out["fallback_reason"] is None
    assert raw["source"] == "api"
    fetcher.fetch.assert_not_called()


def test_api_error_falls_back_to_html(tmp_path: Path):
    def broken():
        raise ApiError("http_429", "slow down")

    run_one(
        _scraper(), _fetcher(HTML_CARD), tmp_path, "devops", FIELDS - {"requirements"}, None, {},
        api_search=broken,
    )
    out = _read(tmp_path, "linkedin.json")
    assert out["source"] == "html"
    assert out["fallback_reason"] == "http_429: slow down"
    assert [j["title"] for j in out["jobs"]] == ["Html Role"]


def test_zero_api_results_is_not_a_fallback(tmp_path: Path):
    fetcher = _fetcher(HTML_CARD)
    run_one(
        _scraper(), fetcher, tmp_path, "devops", FIELDS - {"requirements"}, None, {},
        api_search=lambda: [],
    )
    out = _read(tmp_path, "linkedin.json")
    assert out["count"] == 0
    assert out["source"] == "api"
    fetcher.fetch.assert_not_called()


def test_without_api_search_source_is_html(tmp_path: Path):
    run_one(_scraper(), _fetcher(HTML_CARD), tmp_path, "devops", FIELDS - {"requirements"}, None, {})
    assert _read(tmp_path, "linkedin.json")["source"] == "html"


def test_detail_api_used_then_page_fallback_per_job(tmp_path: Path):
    fetcher = _fetcher("<div class='show-more-less-html__markup'>From page</div>")

    def detail(job):
        if job["job_id"] == "1":
            return "From api"
        raise ApiError("http_500")

    run_one(
        _scraper(), fetcher, tmp_path, "devops", FIELDS, None, {},
        api_search=lambda: [_api_job("1"), _api_job("2")],
        api_detail=detail,
    )
    jobs = {j["title"]: j["requirements"] for j in _read(tmp_path, "linkedin.json")["jobs"]}
    assert jobs["Role 1"] == "From api"
    assert jobs["Role 2"] is not None and "From page" in jobs["Role 2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_runner_api.py -q`
Expected: FAIL with `TypeError: run_one() got an unexpected keyword argument 'api_search'`.

Before implementing, check the LinkedIn detail selector used in the last test: run `grep -n "select_one\|selector" scraper/sites/linkedin.py | head` and make the fixture HTML in `test_detail_api_used_then_page_fallback_per_job` use one of the selectors `LinkedinScraper.parse_detail` already checks.

- [ ] **Step 3: Replace `_fetch_requirements` in `scraper/runner.py`**

Add these imports at the top of `scraper/runner.py` (keep isort order; `ruff check --fix` will sort them):
```python
from collections.abc import Callable

from .api.client import ApiClient, ApiError
from .api.registry import API_SOURCES
from .api.source import search_all
```

Replace the whole `_fetch_requirements` function with:
```python
def _fetch_requirements(
    jobs: list[Job],
    fields: frozenset[str],
    fetcher: FetchChain,
    scraper: Scraper,
    detail: Callable[[Job], str | None] | None = None,
) -> None:
    if "requirements" not in fields or not jobs:
        return

    def _from_page(job: Job) -> str | None:
        url = job.get("url")
        if not url:
            return None
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return None
        if host not in ALLOWED_URL_HOSTS:
            return None
        result = fetcher.fetch(url)
        return scraper.parse_detail(result.html) if result.html else None

    def _fetch_one(job: Job) -> str | None:
        existing = job.get("requirements")
        if isinstance(existing, str) and existing.strip():
            return existing
        if detail is not None:
            try:
                text = detail(job)
            except ApiError as exc:
                _LOG.debug("[%s] detail api failed for %s: %s", scraper.name, job.get("url"), exc)
                text = None
            if text:
                return text
        return _from_page(job)

    _LOG.info("[%s] fetching requirements for %d job(s)", scraper.name, len(jobs))
    with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as ex:
        futures = {ex.submit(_fetch_one, job): i for i, job in enumerate(jobs)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                jobs[idx]["requirements"] = fut.result()
            except Exception:
                jobs[idx]["requirements"] = None
```

Note: one `ApiClient` is shared by the detail threads of a site+keyword. Its pacing flag is a plain bool, and parallel detail calls may sleep at the same moment. That is acceptable (calls are still spaced per thread); do not add locking unless the smoke run shows 429s.

- [ ] **Step 4: Split `run_one` into HTML fetch + shared pipeline**

Add this helper above `run_one`. It is the old fetch/parse block moved out unchanged, plus `fallback_reason` in the failure payloads:
```python
def _html_jobs(
    scraper: Scraper,
    fetcher: FetchChain,
    keyword: str,
    label: str,
    paths: tuple[Path, Path, Path],
    fallback_reason: str | None,
) -> list[Job] | None:
    json_path, raw_path, debug_path = paths
    _LOG.info("[%s] fetching %s", label, scraper.url)
    result = fetcher.fetch(scraper.url)
    html = result.html
    if not html and scraper.requires_search_html:
        _LOG.error("[%s] FAILED: no html", label)
        json_path.write_text(
            json.dumps(
                {
                    "error": "fetch failed",
                    "url": scraper.url,
                    "keyword": keyword,
                    "attempts": [a.to_dict() for a in result.attempts],
                    "source": "html",
                    "fallback_reason": fallback_reason,
                },
                indent=2,
            )
        )
        # keep raw output in lockstep with json_path: reset it so a stale
        # prior-run raw file is never mis-attributed to this failed run
        raw_path.write_text(
            json.dumps(
                {"keyword": keyword, "count": 0, "jobs": [], "error": "fetch failed"},
                indent=2,
            )
        )
        return None

    if html:
        debug_path.write_text(html)
        _LOG.info("[%s] saved raw html → %s (%d bytes)", label, debug_path.name, len(html))
    else:
        _LOG.info("[%s] no search html (scraper handles fetch internally)", label)
    return scraper.parse(html or "")
```

Replace the `run_one` signature and its body from the top down to (and including) `_LOG.info("[%s] parsed %d job(s)", label, parsed_count)` with:
```python
def run_one(
    scraper: Scraper,
    fetcher: FetchChain,
    output_dir: Path,
    keyword: str,
    fields: frozenset[str],
    max_age_hours: int | None,
    content_filter: dict[str, list[str]],
    *,
    api_search: Callable[[], list[Job]] | None = None,
    api_detail: Callable[[Job], str | None] | None = None,
) -> None:
    label = f"{scraper.name}:{keyword_slug(keyword)}"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{scraper.name}.json"
    raw_path = output_dir / f"{scraper.name}.raw.json"
    debug_path = output_dir / f"{scraper.name}.debug.html"

    jobs: list[Job] | None = None
    source = "html"
    fallback_reason: str | None = None
    if api_search is not None:
        try:
            jobs = api_search()
            source = "api"
            _LOG.info("[%s] api returned %d job(s)", label, len(jobs))
        except ApiError as exc:
            fallback_reason = str(exc)
            _LOG.warning("[%s] api failed (%s); falling back to html", label, exc)

    if jobs is None:
        jobs = _html_jobs(
            scraper, fetcher, keyword, label, (json_path, raw_path, debug_path), fallback_reason
        )
        if jobs is None:
            return

    parsed_count = len(jobs)
    _LOG.info("[%s] parsed %d job(s) via %s", label, parsed_count, source)
```

In the rest of `run_one`:
1. In the `raw_path.write_text(json.dumps({...}))` payload, add two keys after `"jobs": raw_jobs,`:
```python
                "source": source,
                "fallback_reason": fallback_reason,
```
2. Change the requirements call to:
```python
    _fetch_requirements(
        jobs, fields, fetcher, scraper, detail=api_detail if source == "api" else None
    )
```
3. In the final `json_path.write_text(json.dumps({...}))` payload, add after `"jobs": projected,`:
```python
                "source": source,
                "fallback_reason": fallback_reason,
```

- [ ] **Step 5: Wire API sources in `run._process`**

In `run()`, replace the `run_one(...)` call inside `_process` with:
```python
        api_search: Callable[[], list[Job]] | None = None
        api_detail: Callable[[Job], str | None] | None = None
        api_cfg = site_cfg.api
        if api_cfg is not None and api_cfg.enabled and name in API_SOURCES:
            api_source = API_SOURCES[name](ApiClient(proxy=proxy_url))
            locations, country_wide = api_cfg.locations, api_cfg.country_wide
            max_age, limit = config.max_age_for(name), config.limit_for(name)

            def _search_api() -> list[Job]:
                return search_all(api_source, keyword, locations, country_wide, max_age, limit)

            api_search = _search_api
            api_detail = api_source.detail
        run_one(
            scraper,
            fetcher,
            keyword_dir,
            keyword,
            config.fields_for(name),
            config.max_age_for(name),
            config.filter_for(name),
            api_search=api_search,
            api_detail=api_detail,
        )
```

- [ ] **Step 6: Run the new tests**

Run: `.venv/bin/python -m pytest tests/test_runner_api.py -q`
Expected: `5 passed`.

- [ ] **Step 7: Run the full suite and lint**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check scraper tests && .venv/bin/mypy scraper`
Expected: all tests pass; ruff and mypy clean. Existing runner tests (`test_runner_raw.py`, `test_runner_bail.py`, `test_filter_before_limit.py`) must pass unchanged — they call `run_one` without the new keyword args. If a test asserts the exact raw/filtered payload dict, add the `source` and `fallback_reason` keys to its expected value.

- [ ] **Step 8: Commit**

```bash
git add scraper/runner.py tests/test_runner_api.py
git commit -m "feat: run API sources first and fall back to HTML per site and keyword"
```

---

### Task 9: `run_metadata.per_site_sources` in the MCP server

**Files:**
- Modify: `mcp_server/server.py` (new `_build_per_site_sources`, used in the `mongo.insert_run` call)
- Test: `tests/test_server_sources.py`

- [ ] **Step 1: Write the failing test**

`tests/test_server_sources.py`:
```python
from __future__ import annotations

from mcp_server.server import _build_per_site_sources


def test_builds_one_entry_per_site_and_keyword():
    filtered = [
        {"keyword": "devops", "site": "jobstreet", "payload": {"source": "api", "fallback_reason": None}},
        {"keyword": "devops", "site": "glints", "payload": {"source": "html", "fallback_reason": "http_403"}},
        {"keyword": "devops", "site": "indeed", "payload": {"count": 0}},
        {"keyword": "devops", "site": "broken", "payload": "not a dict"},
    ]
    assert _build_per_site_sources(filtered) == [
        {"site": "jobstreet", "keyword": "devops", "source": "api", "fallback_reason": None},
        {"site": "glints", "keyword": "devops", "source": "html", "fallback_reason": "http_403"},
        {"site": "indeed", "keyword": "devops", "source": "html", "fallback_reason": None},
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_server_sources.py -q`
Expected: FAIL with `ImportError: cannot import name '_build_per_site_sources'`.

- [ ] **Step 3: Implement**

Add below `_build_per_site_counts` in `mcp_server/server.py`:
```python
def _build_per_site_sources(filtered_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # list, not a {keyword: ...} map: keywords like "node.js" are unsafe Mongo field names
    sources: list[dict[str, Any]] = []
    for entry in filtered_results:
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            continue
        sources.append(
            {
                "site": entry.get("site"),
                "keyword": entry.get("keyword"),
                "source": payload.get("source", "html"),
                "fallback_reason": payload.get("fallback_reason"),
            }
        )
    return sources
```

In `scrape_jobs`, inside the `"run_metadata": {...}` dict passed to `mongo.insert_run`, add after `"per_site_counts": _build_per_site_counts(results),`:
```python
                    "per_site_sources": _build_per_site_sources(filtered_results),
```

Also update the `get_latest_scrape_run` / `insert_scrape_run` docstring line that lists `run_metadata` keys (`run_metadata: {ok, exit_code, keywords, requested_sites, errors, per_site_counts, bot_post_status}`) to include `per_site_sources`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_server_sources.py tests/test_scrape_jobs_ok.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/server.py tests/test_server_sources.py
git commit -m "feat: record per-site API or HTML source in run metadata"
```

---

### Task 10: Config files and docs

**Files:**
- Modify: `config.yaml` (sites block), `config.dev.patch.yaml`
- Modify: `docs/configuration.md`, `docs/sites.md`

- [ ] **Step 1: Add `api:` blocks to `config.yaml`**

Under `sites.jobstreet`, after `url_template`:
```yaml
    api:
      enabled: true
      # JobStreet `where` labels; Tangerang/Bekasi also return nearby Jakarta jobs (deduped)
      locations: [Jakarta Raya, Bandung Jawa Barat, Bekasi Jawa Barat, Tangerang Banten, Tangerang Selatan Banten]
      country_wide: true
```

Under `sites.glints`:
```yaml
    api:
      enabled: true
      # Glints hierarchical location UUIDs (lookup: searchHierarchicalLocations on https://glints.com/api/graphql)
      locations:
        - 78d63064-78a1-4577-8516-036a6c5e903e  # DKI Jakarta
        - 86a3dc56-1bd7-4cd3-8225-d3e4b976e552  # Bandung
        - 87c39cfb-0e3c-4edb-a7a0-754fb70cc587  # Bekasi
        - ae3c458e-5947-4833-8f1b-e001ce2fad1d  # Tangerang
        - 337f8da8-70d8-4916-9733-1cee8e4902e9  # Tangerang Selatan
      country_wide: true
```

Under `sites.linkedin`:
```yaml
    api:
      enabled: true
      locations: ["Jakarta, Indonesia", "Bandung, Indonesia", "Bekasi, Indonesia", "Tangerang, Indonesia", "Tangerang Selatan, Indonesia"]
      country_wide: true
```

Leave `sites.indeed` unchanged.

- [ ] **Step 2: Dev patch**

In `config.dev.patch.yaml`, set `limit: 30` under `sites.jobstreet` (was `2`). Do not touch the other uncommitted edits in that file. The `api:` blocks come from `config.yaml` through the deep merge in `scripts/test-locally.sh`; check with:

Run: `bash scripts/test-locally.sh --help 2>/dev/null | head -5; grep -n "MERGED_CONFIG" scripts/test-locally.sh | head -3`
Expected: the script merges `config.yaml` + `config.dev.patch.yaml` into `/tmp/config.dev.yaml`.

- [ ] **Step 3: Config loads**

Run: `.venv/bin/python -c "from pathlib import Path; from scraper.config_loader import load; c=load(Path('config.yaml')); print({s.name: s.api for s in c.sites})"`
Expected: `jobstreet`, `glints`, `linkedin` print an `ApiConfig(...)`; `indeed` prints `None`.

- [ ] **Step 4: Docs**

In `docs/configuration.md`, add a section `### sites.<name>.api` describing: `enabled` (default true), `locations` (per-site format: JobStreet `where` label, Glints UUID, LinkedIn place name), `country_wide` (adds one call that keeps only jobs labelled `Indonesia`), and that any API failure reruns that site+keyword with `url_template` (HTML).

In `docs/sites.md`, add per site: primary source (endpoint), fallback (HTML via `url_template`), known limits (Glints 50 jobs per city and needs the `deviceid` cookie; LinkedIn 10 per page and rate-limits fast; JobStreet `where` radius overlap).

- [ ] **Step 5: Commit**

```bash
git add config.yaml config.dev.patch.yaml docs/configuration.md docs/sites.md
git commit -m "feat: enable API-first sources in config and document fallback"
```

(If the user chose in Task 0 to keep their own uncommitted `config.dev.patch.yaml` edits out of this branch, stage only the `limit` hunk with `git add -p config.dev.patch.yaml`.)

---

### Task 11: Live smoke run (manual, not CI)

- [ ] **Step 1: Run the scraper for one keyword**

Run: `.venv/bin/python -m scraper --help` to confirm the CLI flags, then run DevOps on the three sites, e.g.:
```bash
.venv/bin/python -m scraper jobstreet glints linkedin --keyword devops
```
Expected log lines per site: `api returned N job(s)` and `parsed N job(s) via api`. No `falling back to html` unless a site is down.

- [ ] **Step 2: Check the output**

Run: `.venv/bin/python -c "import json,glob; [print(p, (d:=json.load(open(p)))['source'], d['fallback_reason'], d['count'], sum(1 for j in d['jobs'] if j.get('requirements'))) for p in glob.glob('output/devops/*.json') if not p.endswith('.raw.json')]"`
Expected:
- `jobstreet` and `glints`: `source=api`, count well above 2 (dev limit 30), `job_id` set on every job, most jobs with `requirements`.
- `linkedin`: `source=api`.
- Spot-check 3 jobs per site: the `url` opens the right job; `location` is in the allowlist.

- [ ] **Step 3: Force a fallback once**

1. Temporarily set `sites.glints.api.locations` to `["00000000-0000-0000-0000-000000000000"]`, run `.venv/bin/python -m scraper glints --keyword devops`, and confirm `count` is 0 with `source=api` (zero results is not a fallback). Revert.
2. Temporarily set the top-level `proxy: http://127.0.0.1:9` in `config.yaml`, run `.venv/bin/python -m scraper jobstreet --keyword devops`, and confirm the log shows `api failed (runtime_error: ...)` and the output has `fallback_reason` starting with `runtime_error`. The HTML path uses the same dead proxy, so it fails too and writes the `fetch failed` payload; that is expected here. Revert.

- [ ] **Step 4: Through MCP**

Rebuild/restart the dev container (`scripts/test-locally.sh`), call `scrape_jobs(keywords=["DevOps"])` through the backend (`POST /api/jobs/scrape`), and confirm in MongoDB that the newest `scrape_runs.run_metadata.per_site_sources` lists `source: "api"` for the three sites.

---

## Not in this plan

- **Indeed**: already on its GraphQL API; no HTML fallback exists for it. Its date filter and per-city calls can follow later using the same `ApiSource` shape.
- **Glints date filter**: `searchJobsV3` has no known date param; the runner's max-age filter on `createdAt` applies.
- **Glints page 2**: needs a logged-in session; out of scope.
