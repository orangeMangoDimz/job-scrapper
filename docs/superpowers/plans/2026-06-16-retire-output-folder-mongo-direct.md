# Retire `output/` Folder — Persist Scrape Results Straight to Mongo

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop persisting scrape results to the `output/` folder; route them in-memory from the scraper straight to the existing Mongo DB service, with no disk fallback (only a TODO for a future job-queue / event-log service).

**Architecture:** Today the scraper writes per-`(keyword,site)` files (`{site}.json`, `{site}.raw.json`, `{site}.debug.html`) to `output/`, and `scrape_jobs` reads them back to build the Mongo document. `output/` is the *transport* between `run_scraper` and `scrape_jobs`, not redundant storage. We make `run_one`/`run` return the payloads in memory (identical dict shapes), have `scrape_jobs` consume them directly, and fully retire `output/` (config field, Dockerfile mkdir, compose `output-init` service + volume mounts, ignore-file entries). The Mongo document shape stays **byte-identical** so downstream consumers (Discord bot, `get_latest_run`) are unaffected.

**Tech Stack:** Python 3, FastMCP, pymongo, pydantic v2 (`AppConfig`), pytest, Docker Compose.

---

## ⛔ Git policy (READ FIRST — overrides the writing-plans skill template)

This repo **forbids** `git commit` / `git add` / `git push` / branching / PRs unless the user explicitly instructs that exact action. The writing-plans skill's "Commit" steps are therefore **replaced by `Checkpoint` steps** (run the full suite). **Do not commit, stage, or even suggest committing.** Leave all changes uncommitted; the user controls git history.

## Conventions for every task

- **Run tests with the venv:** `.venv/bin/python -m pytest` (system Python has no deps). Never bare `pytest`.
- **TDD on a refactor:** here "write the failing test" means *rewrite the existing test to the new contract* — it will fail against the current file-writing code (RED), then pass after the implementation (GREEN).
- **Logger:** never `print()`; the runner already uses `from .log import get_logger` with loguru `{}`-style placeholders. Keep that style.
- **Lint/type:** only via `pre-commit run --all-files` (system `ruff`/`mypy` are absent). Done once at the end (Task 6).

## File map

| File | Change |
|------|--------|
| `scraper/runner.py` | Add `SiteRunResult`; `run_one` returns it (no file writes); `run` returns `(int, list[SiteRunResult])`; drop `output_dir`, `import json`, `from pathlib import Path`. |
| `scraper/__main__.py` | Unpack `run()` tuple, return the int. |
| `mcp_server/server.py` | Delete `_read_site_output` / `_read_site_raw_output`; `scrape_jobs` consumes the structs; add TODO in Mongo `except`. |
| `scraper/config_loader.py` | Drop `output_dir` field (L80) + before-validator entry (L160). |
| `config.yaml` | Drop `output_dir: output`. |
| `Dockerfile` | `mkdir -p /app/output` → `mkdir -p /app`. |
| `docker-compose.yml` | Delete `output-init` service + its `depends_on` refs + both `./output:…` mounts. |
| `.gitignore` | Drop `output/*`, `!output/.gitkeep`. |
| `.dockerignore` | Drop `output`, `*.debug.html`. |
| `tests/test_runner_raw.py` | Assert returned `SiteRunResult`, not files. |
| `tests/test_runner_bail.py` | Assert returned `SiteRunResult`, not files. |
| `tests/test_filter_before_limit.py` | Two `run_one` tests assert returned struct; parse-only tests untouched. |
| `tests/test_scrape_jobs_ok.py` | Mock `run_scraper` → `(0, [SiteRunResult(...)])`; drop `_read_site_*` patches. |
| `tests/test_main_cli.py` | Add a test for the tuple-unpack return. |

**Not done without an explicit follow-up instruction:**
- `output/.gitkeep` is a *tracked* file — do **not** `git rm` it. It leaves an empty tracked dir; flag it to the user at the end.
- Docs (`README.md`, `docs/configuration.md`, `docs/architecture.md`) reference `output_dir`/the output flow — out of scope unless the user opted into doc updates.
- The commented-out `scraper` service in `docker-compose.yml` references `output` — leave it (dead comment).

---

## Task 1: `scraper/runner.py` — return results in memory

**Files:**
- Modify: `scraper/runner.py` (imports; add `SiteRunResult`; rewrite `run_one`, `run`, `_process`)
- Modify: `scraper/__main__.py:42-49`
- Test: `tests/test_runner_raw.py`, `tests/test_runner_bail.py`, `tests/test_filter_before_limit.py`, `tests/test_main_cli.py`

- [ ] **Step 1: Rewrite `tests/test_runner_raw.py` to assert the returned struct (failing test)**

Replace the **entire file** with:

```python
from __future__ import annotations

from unittest.mock import MagicMock

from scraper import runner


def _job(title: str, location: str) -> dict:
    return {"title": title, "company": "ACME", "url": f"https://x/{title}", "location": location}


def test_run_one_returns_raw_before_filter():
    """raw holds ALL parsed jobs; filtered is cut down by filter + limit."""
    scraper = MagicMock()
    scraper.name = "fake"
    scraper.url = "https://example.test/search"
    scraper.limit = 5
    scraper.requires_search_html = True
    scraper.parse.return_value = [
        _job("A", "Jakarta"),
        _job("B", "Jakarta"),
        _job("C", "Surabaya"),
    ]

    fetcher = MagicMock()
    fetcher.fetch.return_value.html = "<html>ok</html>"
    fetcher.fetch.return_value.attempts = []

    result = runner.run_one(
        scraper,
        fetcher,
        "data analyst",
        frozenset({"title", "company", "url", "location"}),
        None,  # max_age_hours
        {"location": ["jakarta"]},  # content_filter drops Surabaya
    )

    assert result.keyword == "data analyst"
    assert result.site == "fake"
    assert result.raw["count"] == 3  # all parsed jobs survive
    assert {j["title"] for j in result.raw["jobs"]} == {"A", "B", "C"}
    assert result.filtered["count"] == 2  # Surabaya filtered out
    assert {j["title"] for j in result.filtered["jobs"]} == {"A", "B"}


def test_run_one_returns_reset_raw_on_fetch_failure():
    """A fetch failure yields an error-marked `filtered` + empty `raw`.

    In-memory results can't carry across runs, so the file-staleness class the
    old disk-based code guarded against (output/ was a persistent volume) no
    longer exists.
    """
    scraper = MagicMock()
    scraper.name = "fake"
    scraper.url = "https://example.test/search"
    scraper.limit = 5
    scraper.requires_search_html = True
    scraper.parse.return_value = [_job("A", "Jakarta")]

    fetcher = MagicMock()
    fetcher.fetch.return_value.html = ""  # fetch failure
    fetcher.fetch.return_value.attempts = []

    result = runner.run_one(
        scraper,
        fetcher,
        "data analyst",
        frozenset({"title", "company", "url", "location"}),
        None,
        {},
    )

    assert result.filtered == {
        "error": "fetch failed",
        "url": "https://example.test/search",
        "keyword": "data analyst",
        "attempts": [],
    }
    assert result.raw == {
        "keyword": "data analyst",
        "count": 0,
        "jobs": [],
        "error": "fetch failed",
    }
    scraper.parse.assert_not_called()
```

- [ ] **Step 2: Rewrite `tests/test_runner_bail.py` (failing test)**

Replace the **entire file** with:

```python
from __future__ import annotations

from unittest.mock import MagicMock

from scraper.runner import run_one


def _make_fetcher(html: str | None):
    fetcher = MagicMock()
    result = MagicMock()
    result.html = html
    result.attempts = ()
    fetcher.fetch.return_value = result
    return fetcher


def test_run_one_bails_when_html_required_and_missing():
    scraper = MagicMock()
    scraper.name = "glints"
    scraper.url = "https://glints.com/x"
    scraper.requires_search_html = True
    scraper.parse = MagicMock(return_value=[])
    fetcher = _make_fetcher(html=None)

    result = run_one(
        scraper=scraper,
        fetcher=fetcher,
        keyword="data analyst",
        fields=frozenset({"title"}),
        max_age_hours=None,
        content_filter={},
    )

    assert result.filtered == {
        "error": "fetch failed",
        "url": "https://glints.com/x",
        "keyword": "data analyst",
        "attempts": [],
    }
    scraper.parse.assert_not_called()


def test_run_one_skips_bail_for_indeed_style_scraper():
    scraper = MagicMock()
    scraper.name = "indeed"
    scraper.url = "https://id.indeed.com/jobs?q=x"
    scraper.requires_search_html = False
    scraper.limit = 10
    fake_job = {
        "site": "indeed",
        "matched_keyword": "data analyst",
        "title": "API job",
        "company": "ACME",
        "url": "https://id.indeed.com/viewjob?jk=1",
        "requirements": "from API",
        "posted_at": None,
        "posted_date": None,
    }
    scraper.parse = MagicMock(return_value=[fake_job])
    fetcher = _make_fetcher(html=None)

    result = run_one(
        scraper=scraper,
        fetcher=fetcher,
        keyword="data analyst",
        fields=frozenset({"title", "url", "requirements"}),
        max_age_hours=None,
        content_filter={},
    )

    scraper.parse.assert_called_once_with("")
    assert result.filtered["count"] == 1
    assert result.filtered["jobs"][0]["title"] == "API job"
    assert result.filtered["jobs"][0]["requirements"] == "from API"
```

- [ ] **Step 3: Rewrite the two `run_one` tests in `tests/test_filter_before_limit.py` (failing test)**

Edit `tests/test_filter_before_limit.py`. (a) Remove the now-unused imports at the top — delete these two lines:

```python
import json
from pathlib import Path
```

(b) Replace `test_content_filter_runs_before_cap` (the whole function) with:

```python
def test_content_filter_runs_before_cap():
    jobs = [
        _job("Bandung Role A", "B1", "Bandung"),
        _job("Bandung Role B", "B2", "Bandung"),
        _job("Jakarta Role A", "J1", "Jakarta"),
        _job("Jakarta Role B", "J2", "Jakarta"),
        _job("Jakarta Role C", "J3", "Jakarta"),
    ]
    scraper = MagicMock()
    scraper.name = "linkedin"
    scraper.url = "https://www.linkedin.com/jobs/search?keywords=x"
    scraper.requires_search_html = True
    scraper.limit = 2
    scraper.parse = MagicMock(return_value=jobs)

    result = run_one(
        scraper=scraper,
        fetcher=_make_fetcher(html="<html>non-empty</html>"),
        keyword="data analyst",
        fields=frozenset({"title", "location"}),  # no "requirements" → no detail fetch
        max_age_hours=None,
        content_filter={"location": ["jakarta"]},
    )

    assert result.filtered["count"] == 2
    assert all("jakarta" in j["location"].lower() for j in result.filtered["jobs"])
```

(c) Replace `test_max_age_runs_before_cap` (the whole function) with:

```python
def test_max_age_runs_before_cap():
    now = datetime.now(UTC)
    stale = (now - timedelta(hours=100)).isoformat()
    recent = (now - timedelta(hours=1)).isoformat()
    jobs = [
        _job("Stale A", "S1", "Jakarta", posted_at=stale),
        _job("Stale B", "S2", "Jakarta", posted_at=stale),
        _job("Recent A", "R1", "Jakarta", posted_at=recent),
        _job("Recent B", "R2", "Jakarta", posted_at=recent),
        _job("Recent C", "R3", "Jakarta", posted_at=recent),
    ]
    scraper = MagicMock()
    scraper.name = "linkedin"
    scraper.url = "https://www.linkedin.com/jobs/search?keywords=x"
    scraper.requires_search_html = True
    scraper.limit = 2
    scraper.parse = MagicMock(return_value=jobs)

    result = run_one(
        scraper=scraper,
        fetcher=_make_fetcher(html="<html>non-empty</html>"),
        keyword="data analyst",
        fields=frozenset({"title", "posted_at"}),
        max_age_hours=24,
        content_filter={},
    )

    assert result.filtered["count"] == 2
    assert all(j["title"].startswith("Recent") for j in result.filtered["jobs"])
```

> Leave everything from `_LINKEDIN_HTML = …` onward (the parse-only tests) **unchanged**.

- [ ] **Step 4: Add a CLI return test to `tests/test_main_cli.py` (failing test)**

Append to `tests/test_main_cli.py`:

```python
def test_main_returns_exit_code_from_run():
    # run() now returns (exit_code, results); main must surface only the int.
    with (
        patch("scraper.__main__.load", return_value=object()),
        patch("scraper.__main__.run", return_value=(0, [])) as mock_run,
    ):
        rc = main(["jobstreet"])
    assert rc == 0
    mock_run.assert_called_once()
```

- [ ] **Step 5: Run the rewritten tests to verify they FAIL**

Run:
```bash
.venv/bin/python -m pytest tests/test_runner_raw.py tests/test_runner_bail.py tests/test_filter_before_limit.py tests/test_main_cli.py -v
```
Expected: the rewritten tests FAIL — `run_one()` currently requires an `output_dir` positional and returns `None` (so `result.keyword` → `AttributeError`); `test_main_returns_exit_code_from_run` fails because old `main` returns the tuple, not `0`.

- [ ] **Step 6: Update `scraper/runner.py` imports**

Replace the top import block (lines 1–8):

```python
from __future__ import annotations

import json
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
```

with:

```python
from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
```

- [ ] **Step 7: Add the `SiteRunResult` dataclass**

Immediately after the import block and before `def default_fetch_chain(...)`, insert:

```python
@dataclass(frozen=True)
class SiteRunResult:
    """In-memory result of one (keyword, site) scrape.

    ``filtered`` is the post-filter/limit/projection payload (formerly the
    ``{site}.json`` file); ``raw`` is the pre-filter snapshot of all parsed jobs
    (formerly ``{site}.raw.json``). The dict shapes are unchanged so the Mongo
    document and its downstream consumers stay byte-identical.
    """

    keyword: str
    site: str
    filtered: dict[str, Any]
    raw: dict[str, Any]
```

- [ ] **Step 8: Rewrite `run_one` to return `SiteRunResult` (no file writes)**

Replace the **entire** `def run_one(...)` function with:

```python
def run_one(
    scraper: Scraper,
    fetcher: FetchChain,
    keyword: str,
    fields: frozenset[str],
    max_age_hours: int | None,
    content_filter: dict[str, list[str]],
) -> SiteRunResult:
    label = f"{scraper.name}:{keyword_slug(keyword)}"

    _LOG.info("[{}] fetching {}", label, scraper.url)
    result = fetcher.fetch(scraper.url)
    html = result.html
    if not html and scraper.requires_search_html:
        _LOG.error("[{}] FAILED: no html", label)
        return SiteRunResult(
            keyword=keyword,
            site=scraper.name,
            filtered={
                "error": "fetch failed",
                "url": scraper.url,
                "keyword": keyword,
                "attempts": [a.to_dict() for a in result.attempts],
            },
            raw={"keyword": keyword, "count": 0, "jobs": [], "error": "fetch failed"},
        )

    if html:
        _LOG.info("[{}] fetched search html ({} bytes)", label, len(html))
    else:
        _LOG.info("[{}] no search html (scraper handles fetch internally)", label)

    jobs = scraper.parse(html or "")
    parsed_count = len(jobs)
    _LOG.info("[{}] parsed {} job(s)", label, parsed_count)

    _enrich_jobs(jobs, keyword)

    # snapshot ALL parsed jobs (only the site's query-param filtering applied) BEFORE
    # any Python-level filter/limit/projection. project_jobs builds fresh dicts, so the
    # later in-place requirements enrichment cannot leak back into this raw record.
    raw_jobs = project_jobs(jobs, CANONICAL_FIELDS)
    raw_payload = {
        "keyword": keyword,
        "fields": sorted(CANONICAL_FIELDS),
        "count": len(raw_jobs),
        "jobs": raw_jobs,
    }
    _LOG.info("[{}] captured {} raw job(s)", label, len(raw_jobs))

    cutoff: datetime | None = None
    if max_age_hours is not None:
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
        before = len(jobs)
        recent: list[Job] = []
        for job in jobs:
            if _within_max_age(job, cutoff):
                recent.append(job)
            else:
                _LOG.debug(
                    "[{}] drop stale: {!r} posted_at={} < cutoff={}",
                    label,
                    job.get("title"),
                    job.get("posted_at"),
                    cutoff.isoformat(),
                )
        jobs = recent
        _LOG.info(
            "[{}] max_age={}h cutoff={} kept {}/{} (dropped {} stale)",
            label,
            max_age_hours,
            cutoff.isoformat(),
            len(jobs),
            before,
            before - len(jobs),
        )

    if content_filter:
        before = len(jobs)
        matched: list[Job] = []
        for job in jobs:
            reason = filter_reason(job, content_filter)
            if reason is None:
                matched.append(job)
            else:
                _LOG.debug("[{}] drop filter: {!r} {}", label, job.get("title"), reason)
        jobs = matched
        _LOG.info(
            "[{}] filter={} kept {}/{} (dropped {})",
            label,
            content_filter,
            len(jobs),
            before,
            before - len(jobs),
        )

    if len(jobs) > scraper.limit:
        _LOG.info("[{}] capping {} job(s) to limit={}", label, len(jobs), scraper.limit)
        jobs = jobs[: scraper.limit]

    _fetch_requirements(jobs, fields, fetcher, scraper)

    projected = project_jobs(jobs, fields)
    filtered_payload = {
        "keyword": keyword,
        "fields": sorted(fields),
        "max_age_hours": max_age_hours,
        "filter": content_filter or None,
        "count": len(projected),
        "jobs": projected,
    }
    _LOG.info("[{}] done: {} job(s) after filter/limit", label, len(projected))
    return SiteRunResult(
        keyword=keyword,
        site=scraper.name,
        filtered=filtered_payload,
        raw=raw_payload,
    )
```

- [ ] **Step 9: Rewrite `run` to drop `output_dir` and return `(int, list[SiteRunResult])`**

Replace the **entire** `def run(...)` function with:

```python
def run(
    config: AppConfig,
    targets: Iterable[str] = (),
    keywords: Iterable[str] | None = None,
) -> tuple[int, list[SiteRunResult]]:
    selected = _select_targets(config, targets)
    if not selected:
        _LOG.error("[runner] no sites selected (none enabled in config and no CLI args)")
        return 1, []

    unknown = [name for name in selected if name not in SCRAPERS]
    if unknown:
        _LOG.error(
            "[runner] unknown sites: {}. available: {}",
            ", ".join(unknown),
            ", ".join(SCRAPERS),
        )
        return 1, []

    keyword_list = list(keywords) if keywords else list(config.keywords)
    if not keyword_list:
        _LOG.error("[runner] no keywords to scrape")
        return 1, []

    pairs = _build_pairs(selected, keyword_list)
    proxy_url = config.proxy.url if config.proxy else None
    if proxy_url:
        _LOG.info("[runner] using proxy: {}", proxy_url)
    fetcher = default_fetch_chain(proxy=proxy_url, tuning=config.timeouts)

    # Load the wilayah location index fresh from Mongo once, single-threaded, before
    # workers fan out. Reflects current data each run; threads then read it via
    # get_index() during filtering. Degrades to legacy substring if Mongo is absent.
    refresh_index()

    def _process(pair: tuple[str, str]) -> SiteRunResult | None:
        keyword, name = pair
        site_cfg = config.site(name)
        if site_cfg is None:
            _LOG.warning("[runner] '{}' has no entry in config.yaml; skipping", name)
            return None
        scraper_cls = SCRAPERS[name]
        url = site_cfg.url_for(keyword)
        scraper = scraper_cls(url=url, limit=config.limit_for(name), tuning=config.timeouts)
        return run_one(
            scraper,
            fetcher,
            keyword,
            config.fields_for(name),
            config.max_age_for(name),
            config.filter_for(name),
        )

    workers = max(1, min(config.concurrency, len(pairs)))
    if workers == 1 or len(pairs) == 1:
        serial: list[SiteRunResult] = [r for pair in pairs if (r := _process(pair)) is not None]
        return 0, serial

    _LOG.info(
        "[runner] running {} (keyword,site) pair(s) with concurrency={}",
        len(pairs),
        workers,
    )
    results: list[SiteRunResult] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scraper") as ex:
        futures = {ex.submit(_process, pair): pair for pair in pairs}
        for fut in as_completed(futures):
            keyword, name = futures[fut]
            try:
                site_result = fut.result()
            except Exception as exc:
                _LOG.error("[{}:{}] thread error: {}", name, keyword_slug(keyword), exc)
                continue
            if site_result is not None:
                results.append(site_result)
    return 0, results
```

- [ ] **Step 10: Update `scraper/__main__.py` to unpack the tuple**

In `scraper/__main__.py`, replace the final line of `main` (currently `return run(config, targets=args.sites, keywords=args.keywords)`) with:

```python
    exit_code, _ = run(config, targets=args.sites, keywords=args.keywords)
    return exit_code
```

- [ ] **Step 11: Run the Task-1 tests to verify they PASS**

Run:
```bash
.venv/bin/python -m pytest tests/test_runner_raw.py tests/test_runner_bail.py tests/test_filter_before_limit.py tests/test_main_cli.py -v
```
Expected: PASS (all).

- [ ] **Step 12: Checkpoint — full suite still green**

Run:
```bash
.venv/bin/python -m pytest -q
```
Expected: PASS. (`test_scrape_jobs_ok.py` still passes here because it mocks both `run_scraper` and `_read_site_*`; the real server path is fixed in Task 2.)

---

## Task 2: `mcp_server/server.py` — consume structs, drop readers, add Mongo TODO

**Files:**
- Modify: `mcp_server/server.py` (delete `_read_site_output`/`_read_site_raw_output`; rewrite the read-back block in `scrape_jobs`; add TODO in the Mongo `except`)
- Test: `tests/test_scrape_jobs_ok.py`

- [ ] **Step 1: Rewrite `tests/test_scrape_jobs_ok.py` (failing test)**

Replace the **entire file** with:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

from scraper.runner import SiteRunResult
from scraper.types import JOB_FIELD_ORDER


def _make_config(keyword: str = "data analyst", site: str = "jobstreet"):
    cfg = MagicMock()
    cfg.keywords = (keyword,)
    cfg.enabled_site_names.return_value = (site,)
    return cfg


def _result(keyword, site, filtered, raw=None):
    return SiteRunResult(
        keyword=keyword,
        site=site,
        filtered=filtered,
        raw=raw if raw is not None else {"keyword": keyword, "fields": [], "count": 0, "jobs": []},
    )


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_ok_true_when_zero_jobs(mock_run, mock_load, mock_mongo):
    """0 jobs returned but fetch succeeded → ok must be True."""
    mock_load.return_value = _make_config()
    mock_run.return_value = (
        0,
        [
            _result(
                "data analyst",
                "jobstreet",
                {
                    "keyword": "data analyst",
                    "fields": ["title"],
                    "count": 0,
                    "jobs": [],
                    "max_age_hours": 24,
                    "filter": None,
                },
            )
        ],
    )

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["results"][0]["sites"][0]["count"] == 0


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_ok_true_when_jobs_found(mock_run, mock_load, mock_mongo):
    """Jobs found → ok must be True."""
    mock_load.return_value = _make_config()
    mock_run.return_value = (
        0,
        [
            _result(
                "data analyst",
                "jobstreet",
                {
                    "keyword": "data analyst",
                    "fields": ["title"],
                    "count": 2,
                    "jobs": [{"title": "A"}, {"title": "B"}],
                    "max_age_hours": 24,
                    "filter": None,
                },
            )
        ],
    )

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["results"][0]["sites"][0]["count"] == 2


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_ok_false_when_fetch_failed(mock_run, mock_load, mock_mongo):
    """Fetch failed → ok must be False, error captured, sites list empty."""
    mock_load.return_value = _make_config()
    mock_run.return_value = (
        0,
        [
            _result(
                "data analyst",
                "jobstreet",
                {
                    "error": "fetch failed",
                    "url": "https://example.com",
                    "keyword": "data analyst",
                },
            )
        ],
    )

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is False
    assert len(result["errors"]) == 1
    assert result["errors"][0]["reason"] == "fetch failed"
    assert result["results"][0]["sites"] == []


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_ok_false_when_site_result_missing(mock_run, mock_load, mock_mongo):
    """A requested (keyword, site) with no result from the scraper → ok False."""
    mock_load.return_value = _make_config()
    mock_run.return_value = (0, [])  # nothing came back for the requested pair

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is False
    assert len(result["errors"]) == 1
    assert result["results"][0]["sites"] == []


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._write_status")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_scrape_jobs_writes_status(mock_run, mock_load, mock_write_status, mock_mongo):
    """scrape_jobs must call _write_status exactly once after a run."""
    mock_load.return_value = _make_config()
    mock_run.return_value = (
        0,
        [
            _result(
                "data analyst",
                "jobstreet",
                {
                    "keyword": "data analyst",
                    "fields": ["title"],
                    "count": 1,
                    "jobs": [{"title": "A"}],
                    "max_age_hours": None,
                    "filter": None,
                },
            )
        ],
    )

    from mcp_server.server import scrape_jobs

    scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    mock_write_status.assert_called_once()
    result_arg, duration_arg = mock_write_status.call_args.args
    assert result_arg["ok"] is True
    assert isinstance(duration_arg, float)


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_scrape_jobs_normalizes_jobs_to_canonical_schema(mock_run, mock_load, mock_mongo):
    mock_load.return_value = _make_config()
    mock_run.return_value = (
        0,
        [
            _result(
                "data analyst",
                "jobstreet",
                {
                    "keyword": "data analyst",
                    "fields": ["title", "company", "url"],
                    "count": 1,
                    "jobs": [
                        {
                            "title": "Data Analyst",
                            "company": "ACME",
                            "url": "https://example.com/job/1",
                            "extra": "drop-me",
                        }
                    ],
                    "max_age_hours": 24,
                    "filter": None,
                },
            )
        ],
    )

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])
    site_entry = result["results"][0]["sites"][0]
    job = site_entry["jobs"][0]

    assert set(job.keys()) == set(JOB_FIELD_ORDER)
    assert job["site"] == "jobstreet"
    assert job["matched_keyword"] == "data analyst"
    assert "extra" not in job
    assert site_entry["count"] == 1


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_scrape_jobs_returns_mongo_id_and_builds_document(mock_run, mock_load, mock_mongo):
    """One document per run: raw_results (all jobs) + filtered_results (cut-down) + per_site_counts."""
    mock_load.return_value = _make_config()
    mock_run.return_value = (
        0,
        [
            _result(
                "data analyst",
                "jobstreet",
                filtered={
                    "keyword": "data analyst",
                    "fields": ["title"],
                    "count": 2,
                    "jobs": [{"title": "A"}, {"title": "B"}],
                    "max_age_hours": 24,
                    "filter": None,
                },
                raw={
                    "keyword": "data analyst",
                    "fields": list(JOB_FIELD_ORDER),
                    "count": 5,
                    "jobs": [{"title": t} for t in "ABCDE"],
                },
            )
        ],
    )
    mock_mongo.insert_run.return_value = "deadbeef"

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["mongo_id"] == "deadbeef"
    doc = mock_mongo.insert_run.call_args.args[0]
    assert doc["raw_results"][0]["payload"]["count"] == 5  # all jobs
    assert doc["filtered_results"][0]["payload"]["count"] == 2  # cut-down list
    assert doc["run_metadata"]["per_site_counts"] == {"jobstreet": {"data analyst": 2}}
    assert "raw_results" not in doc["run_metadata"]  # not nested
    assert doc["note"] is None  # no errors → no note


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_scrape_jobs_sets_note_on_error(mock_run, mock_load, mock_mongo):
    mock_load.return_value = _make_config()
    mock_run.return_value = (
        0,
        [
            _result(
                "data analyst",
                "jobstreet",
                {"error": "fetch failed", "url": "https://x", "keyword": "data analyst"},
            )
        ],
    )
    mock_mongo.insert_run.return_value = "id1"

    from mcp_server.server import scrape_jobs

    scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])
    doc = mock_mongo.insert_run.call_args.args[0]
    assert doc["note"] is not None and "jobstreet" in doc["note"]


def test_get_scrape_response_structure_exposes_canonical_fields():
    from mcp_server.server import get_scrape_response_structure

    out = get_scrape_response_structure()

    assert out["tool"] == "scrape_jobs"
    assert out["job_fields"] == list(JOB_FIELD_ORDER)
    assert out["top_level_fields"] == [
        "ok",
        "keywords",
        "requested_sites",
        "exit_code",
        "results",
        "errors",
        "mongo_id",
    ]
```

- [ ] **Step 2: Run the rewritten test to verify it FAILS**

Run:
```bash
.venv/bin/python -m pytest tests/test_scrape_jobs_ok.py -v
```
Expected: FAIL. The current `scrape_jobs` does `exit_code: int = run_scraper(...)` (now a tuple) and reads files via `_read_site_*`; the new test no longer patches the readers and returns a tuple, so the production code raises / mis-reads.

- [ ] **Step 3: Delete the two file-reader helpers**

In `mcp_server/server.py`, delete the entire `_read_site_output` and `_read_site_raw_output` functions (the block currently at lines 65–82, including the blank line between them).

- [ ] **Step 4: Rewrite the scrape + read-back block in `scrape_jobs`**

Find this block (currently ~lines 703–741):

```python
    # run scraper — writes per-site JSON output files
    exit_code: int = run_scraper(config, targets=target_sites, keywords=target_keywords)

    # read output files: raw (all jobs) + filtered (post-filter) payloads for Mongo,
    # normalize the filtered jobs for the response
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    filtered_results: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    for keyword in target_keywords:
        per_site: list[dict[str, Any]] = []
        for name in target_sites:
            raw_payload = _read_site_raw_output(config, keyword, name)
            if raw_payload is not None:
                raw_results.append({"keyword": keyword, "site": name, "payload": raw_payload})

            payload = _read_site_output(config, keyword, name)
            if payload is None:
                errors.append(
                    {"keyword": keyword, "site": name, "reason": "missing or invalid output JSON"}
                )
                continue
            filtered_results.append({"keyword": keyword, "site": name, "payload": payload})
            if isinstance(payload, dict) and "error" in payload:
                err: dict[str, Any] = {
                    "keyword": keyword,
                    "site": name,
                    "reason": str(payload.get("error")),
                }
                attempts = payload.get("attempts")
                if isinstance(attempts, list):
                    err["attempts"] = attempts
                errors.append(err)
                continue
            normalized_site = _normalize_site_payload(
                payload=payload, site_name=name, keyword=keyword
            )
            per_site.append(normalized_site)
        results.append({"keyword": keyword, "sites": per_site})
```

Replace it with:

```python
    # scrape in-process; results come back in memory (no output/ disk round-trip)
    exit_code, site_results = run_scraper(config, targets=target_sites, keywords=target_keywords)
    by_pair = {(r.keyword, r.site): r for r in site_results}

    # build raw (all jobs) + filtered (post-filter) payloads for Mongo, normalize
    # the filtered jobs for the response
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    filtered_results: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    for keyword in target_keywords:
        per_site: list[dict[str, Any]] = []
        for name in target_sites:
            site_result = by_pair.get((keyword, name))
            if site_result is None:
                errors.append(
                    {"keyword": keyword, "site": name, "reason": "scraper produced no result"}
                )
                continue
            raw_results.append({"keyword": keyword, "site": name, "payload": site_result.raw})
            payload = site_result.filtered
            filtered_results.append({"keyword": keyword, "site": name, "payload": payload})
            if isinstance(payload, dict) and "error" in payload:
                err: dict[str, Any] = {
                    "keyword": keyword,
                    "site": name,
                    "reason": str(payload.get("error")),
                }
                attempts = payload.get("attempts")
                if isinstance(attempts, list):
                    err["attempts"] = attempts
                errors.append(err)
                continue
            normalized_site = _normalize_site_payload(
                payload=payload, site_name=name, keyword=keyword
            )
            per_site.append(normalized_site)
        results.append({"keyword": keyword, "sites": per_site})
```

> Note: `exit_code` keeps its meaning (the runner's int). The `: int` annotation is dropped because it's now unpacked from a tuple; type is inferred. `site_results` is `list[SiteRunResult]`; no new import is needed in `server.py` (only attribute access).

- [ ] **Step 5: Add the no-fallback TODO to the Mongo `except` block**

Find (currently ~lines 784–785):

```python
    except Exception as exc:
        log.error("scrape_jobs: mongo insert failed: {}", exc)
```

Replace with:

```python
    except Exception as exc:
        log.error("scrape_jobs: mongo insert failed: {}", exc)
        # TODO: no durable fallback — a failed Mongo insert drops this run's
        # results entirely (the output/ disk persistence was retired). Add a
        # job-queue or event-log service to capture failed writes and replay
        # them, so a transient Mongo outage doesn't lose scraped data.
```

- [ ] **Step 6: Run the Task-2 test to verify it PASSES**

Run:
```bash
.venv/bin/python -m pytest tests/test_scrape_jobs_ok.py -v
```
Expected: PASS (all).

- [ ] **Step 7: Checkpoint — full suite green**

Run:
```bash
.venv/bin/python -m pytest -q
```
Expected: PASS.

---

## Task 3: Drop `output_dir` from config

**Files:**
- Modify: `scraper/config_loader.py:80`, `scraper/config_loader.py:160`
- Modify: `config.yaml:16`

- [ ] **Step 1: Remove the `output_dir` field from `AppConfig`**

In `scraper/config_loader.py`, delete this line (line 80, inside `class AppConfig(BaseModel)`):

```python
    output_dir: Path
```

- [ ] **Step 2: Remove the `output_dir` entry from the before-validator dict**

In `scraper/config_loader.py`, delete this line (line ~160, inside the returned dict):

```python
            "output_dir": Path(str(raw.get("output_dir", "output"))),
```

> Leave the `from pathlib import Path` import — `load(path: Path)` still uses it.

- [ ] **Step 3: Remove `output_dir` from `config.yaml`**

In `config.yaml`, delete this line (line 16):

```yaml
output_dir: output
```

- [ ] **Step 4: Checkpoint — full suite green + config still loads**

Run:
```bash
.venv/bin/python -m pytest -q
.venv/bin/python -c "from scraper.config_loader import load; from pathlib import Path; c = load(Path('config.yaml')); print('loaded ok; has output_dir:', hasattr(c, 'output_dir'))"
```
Expected: pytest PASS; the second command prints `loaded ok; has output_dir: False` (no `ConfigError`, no extra-field error — pydantic ignores the now-absent key).

---

## Task 4: Retire `output/` infra (Dockerfile, compose, ignore files)

**Files:**
- Modify: `Dockerfile:27`
- Modify: `docker-compose.yml` (delete `output-init` service + refs + mounts)
- Modify: `.gitignore:55-56`
- Modify: `.dockerignore:13-14`

- [ ] **Step 1: Dockerfile — stop creating `/app/output`**

In `Dockerfile`, replace (lines 27–28):

```dockerfile
RUN mkdir -p /app/output \
 && chown -R pwuser:pwuser /app
```

with:

```dockerfile
RUN mkdir -p /app \
 && chown -R pwuser:pwuser /app
```

> `/app` must still be created here (WORKDIR/COPY come later), hence `mkdir -p /app`.

- [ ] **Step 2: docker-compose.yml — delete the `output-init` service**

Delete lines 1–11 (the `output-init` service and its trailing blank line), i.e. from `  # SERVICE: output-init …` through the blank line before `  # SERVICE: scraper …`:

```yaml
  # SERVICE: output-init — fixes output dir ownership before scraper runs (Playwright image runs as root)
  output-init:
    image: mcr.microsoft.com/playwright/python:v1.59.0-noble
    container_name: job-scraper-init
    user: "0:0"
    entrypoint: ["sh", "-c", "chown -R pwuser:pwuser /out"]
    restart: "no"
    volumes:
      - ./output:/out

```

> Keep the `services:` line at the top.

- [ ] **Step 3: docker-compose.yml — drop `output-init` from `scraper-mcp.depends_on` and its output volume**

In the `scraper-mcp` service, change `depends_on` from:

```yaml
    depends_on:
      output-init:
        condition: service_completed_successfully
      mongo:
        condition: service_healthy
```

to:

```yaml
    depends_on:
      mongo:
        condition: service_healthy
```

And in its `volumes`, delete the `./output` mount so:

```yaml
    volumes:
      - ./output:/app/output
      - ./docs:/app/docs:ro
```

becomes:

```yaml
    volumes:
      - ./docs:/app/docs:ro
```

- [ ] **Step 4: docker-compose.yml — drop `output-init` dep + output volume from `bot`**

In the `bot` service, delete the entire `depends_on` block (it only contained `output-init`):

```yaml
    depends_on:
      output-init:
        condition: service_completed_successfully
```

And delete its output volume — change:

```yaml
    volumes:
      - ${CLAUDE_CONFIG_DIR:-~/.claude}:/home/node/.claude
      - ${CLAUDE_CONFIG_FILE:-~/.claude.json}:/home/node/.claude.json
      - ./output:/workspace/output
```

to:

```yaml
    volumes:
      - ${CLAUDE_CONFIG_DIR:-~/.claude}:/home/node/.claude
      - ${CLAUDE_CONFIG_FILE:-~/.claude.json}:/home/node/.claude.json
```

- [ ] **Step 5: `.gitignore` — drop the output entries**

Delete these two lines (55–56):

```
output/*
!output/.gitkeep
```

- [ ] **Step 6: `.dockerignore` — drop the output entries**

Delete these two lines (13–14):

```
output
*.debug.html
```

- [ ] **Step 7: Verify compose still parses**

Run:
```bash
docker compose -f docker-compose.yml config >/dev/null && echo "compose OK"
docker compose -f docker-compose.yml -f docker-compose.dev.yml config >/dev/null && echo "dev overlay OK"
```
Expected: prints `compose OK` and `dev overlay OK` with no `output-init`/`./output` references and no YAML error. (If `docker` is unavailable on the host, eyeball the file: no `output-init`, no `./output:` mounts, every service's `depends_on` is either gone or non-empty.)

---

## Task 5: Final verification

- [ ] **Step 1: Full unit/integration suite**

Run:
```bash
.venv/bin/python -m pytest -q
```
Expected: PASS, no skips related to this change.

- [ ] **Step 2: Confirm no lingering `output/` references in code**

Run:
```bash
grep -rn "output_dir\|_read_site_\|\.raw\.json\|\.debug\.html\|/app/output\|/workspace/output\|output-init" \
  scraper/ mcp_server/ tests/ Dockerfile docker-compose.yml docker-compose.dev.yml .gitignore .dockerignore
```
Expected: no matches (exit code 1 / empty). Any match is a missed edit — fix it.

- [ ] **Step 3: Lint + type via pre-commit**

Run:
```bash
pre-commit run --all-files
```
Expected: ruff + mypy pass. (Watch for: unused-import `E402`/`F401` in `runner.py` if `json`/`Path` weren't fully removed; `SIM`; mypy on the new `tuple[int, list[SiteRunResult]]` return + `Any`.)

- [ ] **Step 4: Real end-to-end (drive the actual MCP path, not just mocks)**

Per `.claude/rules/testing.md`, a green unit test can hide an integration gap — exercise the real stack. Start the dev `mcp` stack (TUI → `dev` → `mcp` → Start, i.e. `python scripts/manage.py`), then trigger one scrape and confirm:
1. The scrape runs and `scrape_jobs` returns `mongo_id` (not `None`).
2. A new document landed in Mongo (TUI **Mongo** test, or query `scrape_runs` for the latest `_created_at`) with `filtered_results[].payload` and `raw_results[].payload` populated in the **same shape** as before.
3. No file appears under `output/` (the dir stays empty besides the tracked `.gitkeep`).
4. Container logs show the scrape + `scrape_jobs: mongo insert ok id=…` line.

To force a Mongo-failure check of the TODO path (optional): stop the `mongo` service, trigger a scrape, confirm `scrape_jobs` logs `scrape_jobs: mongo insert failed: …`, returns `mongo_id=None`, writes **no** `output/` file, and does not crash.

Expected: results persist to Mongo only; `output/` is never written; failures degrade to a logged error + `mongo_id=None` with no fallback.

- [ ] **Step 5: Report to the user (no commits)**

Summarize the changes and surface the two deferred items: (a) `output/.gitkeep` is still a tracked file (offer to `git rm` it only if they ask); (b) docs referencing `output_dir` (`README.md`, `docs/configuration.md`, `docs/architecture.md`) are now stale — ask whether to update. **Do not commit or stage anything.**

---

## Self-Review

**Spec coverage:**
- "No need to save content result on output/ folder" → Tasks 1 (stop writes), 3 (config), 4 (infra). ✅
- "Instead we already have the DB service here" → Task 2 (`scrape_jobs` feeds `mongo.insert_run` from in-memory structs; doc shape preserved). ✅
- "If it's failed to save on DB, no fallback for now" → Task 2 Step 5 (no fallback; behavior already drops to logged error + `mongo_id=None`). ✅
- "Add TODO to add a new service like job queue or event log here" → Task 2 Step 5 (TODO comment in the Mongo `except`). ✅

**Placeholder scan:** No TBD/TODO-in-plan/"add error handling"/"similar to Task N". The only literal `TODO` is the *intended product artifact* (Task 2 Step 5). ✅

**Type consistency:** `SiteRunResult{keyword, site, filtered, raw}` defined in Task 1 Step 7; used identically in `run_one`/`run` (Task 1), `scrape_jobs` via `.keyword/.site/.raw/.filtered` (Task 2 Step 4), and tests `_result(...)` (Task 2 Step 1). `run` returns `tuple[int, list[SiteRunResult]]`; unpacked as `exit_code, _` (`__main__`, Task 1 Step 10) and `exit_code, site_results` (server, Task 2 Step 4). ✅

**Behavior-preservation checks:**
- Mongo doc shape: `filtered_results`/`raw_results` are `{keyword, site, payload}` with `payload` = the identical dict formerly serialized to `.json`/`.raw.json`. ✅
- Append order in `scrape_jobs` (raw, then filtered, then error-branch) matches the original. ✅
- Fetch-failure payloads (`{"error": "fetch failed", …}` + reset raw) are byte-identical to the old file contents. ✅
