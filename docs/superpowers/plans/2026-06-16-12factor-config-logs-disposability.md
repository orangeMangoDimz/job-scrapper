# 12-Factor Refactor: Config, Logs & Disposability — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> ⚠️ **NO GIT COMMITS / PUSHES WITHOUT EXPLICIT PER-ACTION APPROVAL.** This repo's owner has a hard rule against unattended commits. Every "Checkpoint" step below shows a *suggested* commit message — run it **only** after the user approves that specific commit. Never `git push`, `rm -rf`, or `branch -D` without asking.

> **Branch/PR:** work on a feature branch; PRs go into `dev`, not `main`. Each Phase (A–D) is independently shippable and can be its own PR.

> **Subagents:** Tasks within a phase that touch disjoint files can be dispatched to parallel subagents. Dependency order is noted per task. Phase A (settings) must land before B/C/D.

**Goal:** Centralize all configuration, logging, and lifecycle knobs for the three runtime components (scraper, MCP server, Discord cron bot) so they follow 12-Factor App principles III (config in environment), XI (logs as event streams), and IX (disposability) — and are easy to change from a small set of central files.

**Architecture:** One new `scraper/settings.py` becomes the single source of truth for *environment-derived* config (Mongo connection, log routing) — deduping the `MONGO_*` reads currently copy-pasted in `mcp_server/mongo.py` and `scraper/sites/_location.py`. *Behavioral tuning* (fetch timeouts, claude model) moves out of scattered source constants into `config.yaml`. Logging becomes a single stdout event stream by default (env-tunable level/format, opt-in rotating file). The bot's cron schedule moves from build-time baking to a runtime entrypoint so it changes without a rebuild. Disposability is closed out with a FastMCP lifespan that shuts the Mongo client down cleanly, a Playwright browser-leak fix, and compose stop/init hardening.

**Tech Stack:** Python 3.12, `logging` (stdlib, hand-rolled JSON formatter — no new deps), `pymongo`, `mcp[cli]` FastMCP (lifespan verified present), Docker / docker-compose, `supercronic`, `yq`, `pytest`.

---

## Decisions locked with the user (2026-06-16)

1. **Config reach:** *Centralize + de-bake schedule.* Dedupe env reads, pull scattered constants (fetch timeouts, claude model) into `config.yaml`, document one env contract, AND make `bot.schedule` runtime-changeable (env → crontab at container start). The rest of `config.yaml` stays image-baked.
2. **Logs target:** *stdout default + opt-in file.* Default to a single stdout stream (Factor XI). `LOG_FILE` re-enables a rotating file (keeps `get_scrape_status.recent_logs` and the bot debug log working). Add `LOG_LEVEL` and `LOG_FORMAT` (`plain`|`json`).

## Conventions

- **Run tests:** `.venv/bin/python -m pytest` (system `python` has no deps). Single file: `.venv/bin/python -m pytest tests/test_x.py -v`.
- **Lint/type:** via pre-commit (`ruff`, `mypy`). ruff: `line-length=100`, `E501` ignored, selects `E,F,I,UP,B,C4,SIM`.
- **Style:** frozen dataclasses for DTOs, type annotations on all signatures, immutable updates (build new dicts), early returns.
- **`caplog` does NOT work on this logger:** `get_logger()` sets `propagate = False`, so records never reach the root logger that `caplog` hooks. Assert on output via `capsys` (logs go to **stdout** after B1) instead of `caplog`.
- **Verified (2026-06-16):** only `scraper/sites/base.py` defines `Scraper.__init__`; all four site classes inherit it, so threading a `tuning` kwarg through `base` reaches every scraper (Task A4 is safe as written).

## Three config layers — keep them distinct (avoid the `config*` name collision)

| Layer | File | Holds |
|-------|------|-------|
| Env-derived deploy handles | **`scraper/settings.py`** (new) | Mongo connection + names, log routing/level/format. Read once from `os.environ`. |
| YAML behavior + tuning | `config.yaml` → `scraper/config_loader.py` (`AppConfig`) | keywords, sites, filters, limits, **fetch timeouts (new)**, **bot.model (new)**, bot.schedule. |
| HTTP identity constants | `scraper/config.py` | `USER_AGENT`, `ACCEPT_LANGUAGE`, `CHALLENGE_MARKERS`, **`FetchTuning` dataclass (new home)**. |

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `scraper/settings.py` | Central env-derived settings (Mongo + logging) |
| Create | `tests/test_settings.py` | Tests for settings defaults + env overrides |
| Modify | `mcp_server/mongo.py` | Read settings; add `close()`; drop local `os.environ` |
| Modify | `scraper/sites/_location.py` | Use settings (dedupe); close client via `with` |
| Modify | `tests/test_mongo.py` | Add `close()` tests |
| Modify | `scraper/config.py` | Add `FetchTuning` frozen dataclass |
| Modify | `scraper/config_loader.py` | Parse `timeouts:`; add `timeouts` to `AppConfig` |
| Modify | `config.yaml` | Add `timeouts:` block + `bot.model` |
| Create | `tests/test_config_timeouts.py` | Tests for timeouts parsing/validation |
| Modify | `scraper/fetchers/curl_cffi.py` | Accept `tuning`, use `http_seconds` |
| Modify | `scraper/fetchers/cloudscraper.py` | Accept `tuning`, use `http_seconds` |
| Modify | `scraper/fetchers/playwright.py` | Accept `tuning`; use ms/settle; **fix browser leak** |
| Modify | `scraper/fetchers/base.py` | `FetchChain` already neutral — no change (confirm) |
| Modify | `scraper/sites/base.py` | `Scraper.__init__` accepts optional `tuning` |
| Modify | `scraper/sites/indeed.py` | Use `tuning.indeed_api_seconds` |
| Modify | `scraper/runner.py` | Thread `config.timeouts` into chain + scrapers |
| Modify | `scraper/log.py` | Rewrite: settings-driven, stdout default, opt-in file, JSON option |
| Modify | `tests/test_log.py` | Rewrite for new handler/level/format behavior |
| Modify | `mcp_server/server.py` | Log/status paths from settings; FastMCP `lifespan`; `recent_logs` None-guard |
| Modify | `tests/test_status.py` | Adjust only if `_LOG_PATH` default change requires it |
| Create | `tests/test_lifespan.py` | Test lifespan closes Mongo on shutdown |
| Modify | `scraper/__main__.py` | Route `print()` error through logger |
| Modify | `cron/entrypoint.sh` | Repurpose (currently dead): generate crontab from `BOT_SCHEDULE` at start |
| Modify | `cron/run-scraper.sh` | `CLAUDE_MODEL` env; stdout-default logging, opt-in `BOT_LOG_FILE` |
| Modify | `Dockerfile` | Bot stage: stop baking crontab; entrypoint → `entrypoint.sh` |
| Modify | `docker-compose.yml` | New env vars; `init`, `stop_grace_period` |
| Modify | `docker-compose.dev.yml` | Dev `LOG_LEVEL=DEBUG` + `LOG_FILE` |
| Modify | `docker-compose.prod.yml` | (inherits; confirm no override needed) |
| Modify | `.github/workflows/deploy.yml` | Inject new env vars (vars with defaults) |
| Modify | `.env.example` | Document new env vars |
| Modify | `README.md` | Schedule-no-rebuild, logging knobs, config layers, disposability |
| Modify | `docs/configuration.md` | Central env contract + config.yaml schema |

---

# PHASE A — Centralize config sources (Python)

## Task A1: Central env settings module

**Files:**
- Create: `scraper/settings.py`
- Create: `tests/test_settings.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_settings.py
from __future__ import annotations

import importlib


def _reload(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import scraper.settings as settings_mod

    return importlib.reload(settings_mod)


def test_defaults(monkeypatch):
    for k in (
        "MONGO_URI",
        "MONGO_DB_NAME",
        "MONGO_COLLECTION_NAME",
        "MONGO_SERVER_SELECTION_TIMEOUT_MS",
        "LOG_LEVEL",
        "LOG_FORMAT",
        "LOG_FILE",
    ):
        monkeypatch.delenv(k, raising=False)
    s = _reload(monkeypatch)
    assert s.MONGO_URI == "mongodb://localhost:27017"
    assert s.MONGO_DB_NAME == "job_scraper"
    assert s.MONGO_COLLECTION_NAME == "scrape_runs"
    assert s.MONGO_SERVER_SELECTION_TIMEOUT_MS == 3000
    assert s.LOG_LEVEL == "INFO"
    assert s.LOG_FORMAT == "plain"
    assert s.LOG_FILE == ""


def test_env_overrides(monkeypatch):
    s = _reload(
        monkeypatch,
        MONGO_URI="mongodb://db:27017",
        MONGO_DB_NAME="x",
        MONGO_SERVER_SELECTION_TIMEOUT_MS="500",
        LOG_LEVEL="debug",
        LOG_FORMAT="JSON",
        LOG_FILE="logs/scraper.log",
    )
    assert s.MONGO_URI == "mongodb://db:27017"
    assert s.MONGO_DB_NAME == "x"
    assert s.MONGO_SERVER_SELECTION_TIMEOUT_MS == 500
    assert s.LOG_LEVEL == "DEBUG"  # normalized upper
    assert s.LOG_FORMAT == "json"  # normalized lower
    assert s.LOG_FILE == "logs/scraper.log"
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/python -m pytest tests/test_settings.py -v`
Expected: `ModuleNotFoundError: No module named 'scraper.settings'`

- [ ] **Step 3: Implement `scraper/settings.py`**

```python
# scraper/settings.py
"""Central, env-derived runtime settings (12-Factor III: config in the environment).

Read ONCE from os.environ at import time, with documented defaults. This is the
single source of truth for environment-driven config — the *deploy handles*
(Mongo connection, log routing). YAML behavior/tuning lives in config.yaml
(scraper/config_loader.py); HTTP identity constants live in scraper/config.py.
Keep the three layers separate.
"""
from __future__ import annotations

import os

# --- MongoDB (deploy handle: connection + names) -----------------------------
MONGO_URI: str = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME: str = os.environ.get("MONGO_DB_NAME", "job_scraper")
MONGO_COLLECTION_NAME: str = os.environ.get("MONGO_COLLECTION_NAME", "scrape_runs")
# Bound server selection so a down/unreachable Mongo fails fast instead of
# stalling the /health probe past its curl timeout.
MONGO_SERVER_SELECTION_TIMEOUT_MS: int = int(
    os.environ.get("MONGO_SERVER_SELECTION_TIMEOUT_MS", "3000")
)

# --- Logging (Factor XI: event streams; routing is a deploy concern) ---------
# Level name: DEBUG/INFO/WARNING/ERROR/CRITICAL (normalized upper).
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()
# "plain" (default) or "json" (normalized lower).
LOG_FORMAT: str = os.environ.get("LOG_FORMAT", "plain").lower()
# Empty/unset => stdout only (Factor XI default). Set a path to ALSO write a
# rotating file (kept for get_scrape_status.recent_logs + bot debug workflows).
LOG_FILE: str = os.environ.get("LOG_FILE", "").strip()
LOG_FILE_MAX_BYTES: int = int(os.environ.get("LOG_FILE_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_FILE_BACKUP_COUNT: int = int(os.environ.get("LOG_FILE_BACKUP_COUNT", "3"))

# --- Run-status snapshot (state file, NOT a log) -----------------------------
# Written after each scrape_jobs run; read by get_scrape_status.
STATUS_FILE: str = os.environ.get("STATUS_FILE", "logs/status.json")
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/bin/python -m pytest tests/test_settings.py -v`
Expected: 2 passed

- [ ] **Step 5: Checkpoint** (commit only after approval)

Suggested: `git add scraper/settings.py tests/test_settings.py && git commit -m "feat(config): add central env-derived settings module"`

---

## Task A2: Dedupe Mongo config + graceful close

**Depends on:** A1
**Files:**
- Modify: `mcp_server/mongo.py`
- Modify: `scraper/sites/_location.py`
- Modify: `tests/test_mongo.py`

- [ ] **Step 1: Add failing `close()` tests** to `tests/test_mongo.py`

```python
def test_close_closes_and_resets_client():
    from unittest.mock import MagicMock, patch

    mock_client = MagicMock()
    with patch.object(mongo_module, "_client", mock_client):
        mongo_module.close()
        mock_client.close.assert_called_once()
    assert mongo_module._client is None


def test_close_is_idempotent_when_no_client():
    from unittest.mock import patch

    with patch.object(mongo_module, "_client", None):
        mongo_module.close()  # must not raise
    assert mongo_module._client is None
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/python -m pytest tests/test_mongo.py -k close -v`
Expected: `AttributeError: module 'mcp_server.mongo' has no attribute 'close'`

- [ ] **Step 3: Rewrite `mcp_server/mongo.py`**

Replace the top of the file (imports + the four module constants, lines 1–26) with:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from scraper import settings

_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is None:
        from pymongo import MongoClient  # deferred so import cost is zero when unused

        _client = MongoClient(
            settings.MONGO_URI,
            serverSelectionTimeoutMS=settings.MONGO_SERVER_SELECTION_TIMEOUT_MS,
        )
    return _client


def get_collection() -> Any:
    return _get_client()[settings.MONGO_DB_NAME][settings.MONGO_COLLECTION_NAME]


def close() -> None:
    """Close the shared client and reset it (graceful shutdown). Idempotent."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
```

Leave `ping()`, `insert_run()`, `get_latest_run()`, `update_run()` (lines 33–71) unchanged. (Verified: nothing references the removed module constants `MONGO_URI`/`_DB_NAME`/`_COLLECTION_NAME`/`_SERVER_SELECTION_TIMEOUT_MS` externally.)

- [ ] **Step 4: Dedupe `scraper/sites/_location.py`**

Remove `import os` (line 3 — confirm it is unused elsewhere; it is). Add near the other imports:

```python
from .. import settings
```

Replace `load_index_from_mongo()` body (lines 176–187) — the `os.environ` reads and the bare `MongoClient(...)` — with a `with` block that closes the client:

```python
    try:
        with MongoClient(
            settings.MONGO_URI,
            serverSelectionTimeoutMS=settings.MONGO_SERVER_SELECTION_TIMEOUT_MS,
        ) as client:
            cursor = client[settings.MONGO_DB_NAME]["wilayah"].find(
                {"_id": {"$regex": _KODE_REGEX}}, {"_id": 1, "nama": 1}
            )
            index = build_index_from_rows(
                (doc["_id"], doc.get("nama") or "") for doc in cursor
            )
    except Exception as exc:  # noqa: BLE001 - fail soft by design
        _LOG.warning("[location] wilayah load failed (%s); location filter degraded", exc)
        return None
```

The generator is consumed by `build_index_from_rows` *inside* the `with`, so the cursor is drained before the client closes (disposability win + dedupe).

- [ ] **Step 5: Run full suite, verify pass**

Run: `.venv/bin/python -m pytest tests/test_mongo.py -v`
Expected: all pass (new `close` tests + existing)
Run: `.venv/bin/python -m pytest -v`
Expected: no regressions (location degrade path still soft-fails)

- [ ] **Step 6: Checkpoint** (commit only after approval)

Suggested: `git add mcp_server/mongo.py scraper/sites/_location.py tests/test_mongo.py && git commit -m "refactor(config): read Mongo settings centrally; add mongo.close()"`

---

## Task A3: Fetch tuning in config.yaml

**Depends on:** A1
**Files:**
- Modify: `scraper/config.py`
- Modify: `scraper/config_loader.py`
- Modify: `config.yaml`
- Create: `tests/test_config_timeouts.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config_timeouts.py
from __future__ import annotations

import pytest

from scraper.config import FetchTuning
from scraper.config_loader import ConfigError, _parse_timeouts


def test_defaults_when_absent():
    t = _parse_timeouts(None)
    assert t == FetchTuning()
    assert t.http_seconds == 30
    assert t.playwright_goto_ms == 60_000
    assert t.indeed_api_seconds == 30


def test_partial_override_keeps_other_defaults():
    t = _parse_timeouts({"http_seconds": 10, "playwright_settle_seconds": 1})
    assert t.http_seconds == 10
    assert t.playwright_settle_seconds == 1
    assert t.playwright_goto_ms == 60_000  # untouched default


def test_rejects_non_positive():
    with pytest.raises(ConfigError):
        _parse_timeouts({"http_seconds": 0})


def test_rejects_non_mapping():
    with pytest.raises(ConfigError):
        _parse_timeouts([1, 2, 3])


def test_unknown_key_ignored():
    t = _parse_timeouts({"bogus": 5})
    assert t == FetchTuning()
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/python -m pytest tests/test_config_timeouts.py -v`
Expected: `ImportError: cannot import name 'FetchTuning'`

- [ ] **Step 3: Add `FetchTuning` to `scraper/config.py`**

Append to `scraper/config.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class FetchTuning:
    """Network tuning knobs, sourced from config.yaml `timeouts:`."""

    http_seconds: int = 30  # curl_cffi + cloudscraper GET timeout
    playwright_goto_ms: int = 60_000  # page.goto timeout
    playwright_networkidle_ms: int = 15_000  # wait_for_load_state("networkidle")
    playwright_settle_seconds: int = 2  # post-nav sleep before page.content()
    indeed_api_seconds: int = 30  # indeed GraphQL POST timeout
```

(Move the `from dataclasses import dataclass` to the top import block; keep `from __future__ import annotations` first.)

- [ ] **Step 4: Add parser + `AppConfig` field in `scraper/config_loader.py`**

Add import near the top:

```python
from .config import FetchTuning
```

Add a positive-int field set + parser (place beside the other `_parse_*` helpers):

```python
_TIMEOUT_FIELDS: frozenset[str] = frozenset(
    {
        "http_seconds",
        "playwright_goto_ms",
        "playwright_networkidle_ms",
        "playwright_settle_seconds",
        "indeed_api_seconds",
    }
)


def _parse_timeouts(raw: object) -> FetchTuning:
    if raw is None:
        return FetchTuning()
    if not isinstance(raw, dict):
        raise ConfigError(f"'timeouts' must be a mapping, got {type(raw).__name__}")
    overrides: dict[str, int] = {}
    for key, value in raw.items():
        if key not in _TIMEOUT_FIELDS:
            from .log import get_logger as _get_logger

            _get_logger().warning(
                "[config] timeouts.%s unknown; ignored. allowed: %s",
                key,
                sorted(_TIMEOUT_FIELDS),
            )
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ConfigError(f"timeouts.{key} must be a positive integer, got {value!r}")
        overrides[key] = value
    return FetchTuning(**overrides)
```

Add `timeouts: FetchTuning` to the `AppConfig` dataclass (after `proxy`, with a default so existing constructions stay valid). Use `default_factory` (idiomatic; add `field` to the existing `from dataclasses import dataclass` import → `from dataclasses import dataclass, field`):

```python
    timeouts: FetchTuning = field(default_factory=FetchTuning)
```

In `load()`, before the `return AppConfig(...)`, add:

```python
    timeouts = _parse_timeouts(raw.get("timeouts"))
```

and pass `timeouts=timeouts` into the `AppConfig(...)` constructor.

- [ ] **Step 5: Add `timeouts:` + `bot.model` to `config.yaml`**

Under `bot:` add `model:` (right after `schedule:`):

```yaml
bot:
  schedule: "0 11 * * *"
  model: claude-haiku-4-5-20251001
  max_chars: 1900
```

Add a top-level block (e.g. after `max_age_hours`):

```yaml
# network tuning (seconds unless suffixed _ms); all optional — omitted keys use defaults
timeouts:
  http_seconds: 30
  playwright_goto_ms: 60000
  playwright_networkidle_ms: 15000
  playwright_settle_seconds: 2
  indeed_api_seconds: 30
```

- [ ] **Step 6: Run, verify pass**

Run: `.venv/bin/python -m pytest tests/test_config_timeouts.py -v`
Expected: 5 passed
Run: `.venv/bin/python -m pytest -v`
Expected: no regressions (existing config tests still pass; `AppConfig` gained a defaulted field)

- [ ] **Step 7: Checkpoint** (commit only after approval)

Suggested: `git add scraper/config.py scraper/config_loader.py config.yaml tests/test_config_timeouts.py && git commit -m "feat(config): move fetch timeouts + claude model into config.yaml"`

---

## Task A4: Thread tuning into fetchers, scrapers, runner

**Depends on:** A3
**Files:**
- Modify: `scraper/fetchers/curl_cffi.py`
- Modify: `scraper/fetchers/cloudscraper.py`
- Modify: `scraper/fetchers/playwright.py`
- Modify: `scraper/sites/base.py`
- Modify: `scraper/sites/indeed.py`
- Modify: `scraper/runner.py`
- Create: `tests/test_fetch_tuning.py`

> Note: this is the most invasive task. The Playwright exception-path cleanup (Factor IX) is folded in here since the file is already being edited; see also Task C2 which depends on this. If scope must be trimmed, this whole task can ship as a follow-up PR — the rest of the plan does not depend on it.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_fetch_tuning.py
from __future__ import annotations

from scraper.config import FetchTuning
from scraper.fetchers import CloudscraperFetcher, CurlCffiFetcher, PlaywrightFetcher
from scraper.runner import default_fetch_chain


def test_fetchers_store_tuning():
    t = FetchTuning(http_seconds=7)
    assert CurlCffiFetcher(tuning=t)._tuning.http_seconds == 7
    assert CloudscraperFetcher(tuning=t)._tuning.http_seconds == 7
    assert PlaywrightFetcher(tuning=t)._tuning.http_seconds == 7


def test_fetchers_default_tuning_when_omitted():
    assert CurlCffiFetcher()._tuning == FetchTuning()


def test_default_fetch_chain_passes_tuning():
    t = FetchTuning(http_seconds=9)
    chain = default_fetch_chain(proxy=None, tuning=t)
    # chain stores fetchers privately; assert each got the tuning
    assert all(f._tuning.http_seconds == 9 for f in chain._fetchers)
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/python -m pytest tests/test_fetch_tuning.py -v`
Expected: `TypeError: __init__() got an unexpected keyword argument 'tuning'`

- [ ] **Step 3: Update `scraper/fetchers/curl_cffi.py`**

Change imports + constructor + the `timeout=30`:

```python
from ..config import ACCEPT_LANGUAGE, USER_AGENT, FetchTuning
```

```python
    def __init__(self, proxy: str | None = None, tuning: FetchTuning | None = None) -> None:
        self._proxy = proxy
        self._tuning = tuning or FetchTuning()
```

```python
                timeout=self._tuning.http_seconds,
```

- [ ] **Step 4: Update `scraper/fetchers/cloudscraper.py`** (same pattern)

```python
from ..config import ACCEPT_LANGUAGE, USER_AGENT, FetchTuning
```

```python
    def __init__(self, proxy: str | None = None, tuning: FetchTuning | None = None) -> None:
        self._proxy = proxy
        self._tuning = tuning or FetchTuning()
```

```python
            response = scraper.get(url, timeout=self._tuning.http_seconds, proxies=proxies)
```

- [ ] **Step 5: Update `scraper/fetchers/playwright.py`** (tuning + leak fix)

```python
from ..config import USER_AGENT, FetchTuning
```

```python
    def __init__(self, proxy: str | None = None, tuning: FetchTuning | None = None) -> None:
        self._proxy = proxy
        self._tuning = tuning or FetchTuning()
```

Replace the `with sync_playwright() as p:` body (lines 45–75) so the browser is always torn down (Factor IX — currently leaks on exception) and timeouts come from tuning:

```python
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-gpu",
                    ],
                )
                try:
                    context_kwargs: dict = {
                        "user_agent": USER_AGENT,
                        "locale": "id-ID",
                        "viewport": {"width": 1366, "height": 768},
                    }
                    if self._proxy:
                        context_kwargs["proxy"] = {"server": self._proxy}
                    context = browser.new_context(**context_kwargs)
                    page = context.new_page()
                    if stealth_v2 is not None:
                        stealth_v2().apply_stealth_sync(page)
                    elif stealth_sync is not None:
                        stealth_sync(page)

                    page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self._tuning.playwright_goto_ms,
                    )
                    with contextlib.suppress(Exception):
                        page.wait_for_load_state(
                            "networkidle", timeout=self._tuning.playwright_networkidle_ms
                        )
                    time.sleep(self._tuning.playwright_settle_seconds)
                    html = page.content()
                finally:
                    with contextlib.suppress(Exception):
                        browser.close()
```

(`browser.close()` tears down its contexts and pages; the `finally` guarantees it runs even when `goto`/`content` raise. `contextlib` is already imported.)

- [ ] **Step 6: Update `scraper/sites/base.py`** — optional tuning on `Scraper`

```python
from ..config import FetchTuning
```

```python
    def __init__(self, url: str, limit: int, tuning: FetchTuning | None = None) -> None:
        self.url = url
        self.limit = limit
        self.tuning = tuning or FetchTuning()
```

- [ ] **Step 7: Update `scraper/sites/indeed.py`** — use `indeed_api_seconds`

Change `_fetch_jobs_from_api` to accept a timeout and use it:

```python
def _fetch_jobs_from_api(keyword: str, where: str, limit: int, timeout: int = 30) -> list[dict]:
```

```python
            timeout=timeout,
```

In `IndeedScraper.parse`, pass the tuned value:

```python
        jobs_data = _fetch_jobs_from_api(
            keyword, where, self.limit, timeout=self.tuning.indeed_api_seconds
        )
```

- [ ] **Step 8: Update `scraper/runner.py`** — thread `config.timeouts`

`default_fetch_chain` signature + body:

```python
def default_fetch_chain(
    proxy: str | None = None, tuning: FetchTuning | None = None
) -> FetchChain:
    return FetchChain(
        [
            CurlCffiFetcher(proxy=proxy, tuning=tuning),
            CloudscraperFetcher(proxy=proxy, tuning=tuning),
            PlaywrightFetcher(proxy=proxy, tuning=tuning),
        ]
    )
```

Add import: `from .config import FetchTuning` (top of file).

In `run()`, pass tuning to the chain:

```python
    fetcher = default_fetch_chain(proxy=proxy_url, tuning=config.timeouts)
```

In `_process()`, pass tuning to the scraper:

```python
        scraper = scraper_cls(url=url, limit=config.limit_for(name), tuning=config.timeouts)
```

- [ ] **Step 9: Run, verify pass**

Run: `.venv/bin/python -m pytest tests/test_fetch_tuning.py -v`
Expected: 3 passed
Run: `.venv/bin/python -m pytest -v`
Expected: no regressions (all scrapers still construct; fetchers default tuning when omitted)

- [ ] **Step 10: Checkpoint** (commit only after approval)

Suggested: `git add scraper/fetchers scraper/sites/base.py scraper/sites/indeed.py scraper/runner.py tests/test_fetch_tuning.py && git commit -m "feat(config): thread fetch tuning from config.yaml; fix playwright browser leak"`

---

# PHASE B — Logs as event streams (Python)

## Task B1: Rewrite the central logger (settings-driven)

**Depends on:** A1
**Files:**
- Modify: `scraper/log.py`
- Modify: `tests/test_log.py`

- [ ] **Step 1: Rewrite `tests/test_log.py`** (new contract: 1 stdout handler by default; file is opt-in; level/format from env)

```python
# tests/test_log.py
from __future__ import annotations

import importlib
import logging


def _reload(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import scraper.settings as settings_mod

    importlib.reload(settings_mod)
    import scraper.log as log_mod

    return importlib.reload(log_mod)


def _clear_log_env(monkeypatch):
    for k in ("LOG_LEVEL", "LOG_FORMAT", "LOG_FILE"):
        monkeypatch.delenv(k, raising=False)


def test_named_logger(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear_log_env(monkeypatch)
    log_mod = _reload(monkeypatch)
    assert log_mod.get_logger().name == "job-scraper"


def test_default_is_single_stdout_handler_no_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear_log_env(monkeypatch)
    log_mod = _reload(monkeypatch)
    logger = log_mod.get_logger()
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.StreamHandler)
    assert not (tmp_path / "logs").exists()  # no app-managed file by default


def test_default_level_is_info(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear_log_env(monkeypatch)
    log_mod = _reload(monkeypatch)
    assert log_mod.get_logger().level == logging.INFO


def test_log_file_adds_rotating_handler(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear_log_env(monkeypatch)
    log_mod = _reload(monkeypatch, LOG_FILE="logs/scraper.log")
    logger = log_mod.get_logger()
    assert len(logger.handlers) == 2
    assert (tmp_path / "logs").is_dir()


def test_level_from_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear_log_env(monkeypatch)
    log_mod = _reload(monkeypatch, LOG_LEVEL="DEBUG")
    assert log_mod.get_logger().level == logging.DEBUG


def test_idempotent(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear_log_env(monkeypatch)
    log_mod = _reload(monkeypatch)
    logger = log_mod.get_logger()
    n = len(logger.handlers)
    log_mod.get_logger()
    assert len(logger.handlers) == n


def test_json_format_emits_json(monkeypatch, tmp_path, capsys):
    import json

    monkeypatch.chdir(tmp_path)
    _clear_log_env(monkeypatch)
    log_mod = _reload(monkeypatch, LOG_FORMAT="json")
    log_mod.get_logger().info("hello %s", "world")
    out = capsys.readouterr().out.strip().splitlines()[-1]
    parsed = json.loads(out)
    assert parsed["msg"] == "hello world"
    assert parsed["level"] == "INFO"
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/python -m pytest tests/test_log.py -v`
Expected: failures (current logger makes 2 handlers, level DEBUG, no JSON)

- [ ] **Step 3: Rewrite `scraper/log.py`**

```python
# scraper/log.py
"""Central logger (Factor XI). Defaults to a single STDOUT event stream; set
LOG_FILE to ALSO write a rotating file. Level/format/routing all come from
scraper.settings (env-driven). Hand-rolled JSON formatter keeps this dep-free.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from pathlib import Path

from . import settings

_LOGGER_NAME = "job-scraper"
_PLAIN_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# Reset to False on every module (re)load; set True after first get_logger().
_initialized: bool = False


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _build_formatter() -> logging.Formatter:
    if settings.LOG_FORMAT == "json":
        return _JsonFormatter()
    return logging.Formatter(_PLAIN_FMT)


def _resolve_level() -> int:
    return logging.getLevelNamesMapping().get(settings.LOG_LEVEL, logging.INFO)


def get_logger() -> logging.Logger:
    global _initialized
    logger = logging.getLogger(_LOGGER_NAME)
    if _initialized:
        return logger

    # Clear handlers left from a previous module load (e.g. test reloads).
    logger.handlers.clear()

    level = _resolve_level()
    logger.setLevel(level)
    logger.propagate = False
    fmt = _build_formatter()

    # STDOUT event stream (Factor XI default).
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(level)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # Opt-in rotating file (keeps get_scrape_status.recent_logs + bot debug log).
    if settings.LOG_FILE:
        log_path = Path(settings.LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=settings.LOG_FILE_MAX_BYTES,
            backupCount=settings.LOG_FILE_BACKUP_COUNT,
            encoding="utf-8",
        )
        fh.setLevel(level)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    _initialized = True
    return logger
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/bin/python -m pytest tests/test_log.py -v`
Expected: all pass
Run: `.venv/bin/python -m pytest -v`
Expected: no regressions (other modules call `get_logger()` the same way)

- [ ] **Step 5: Checkpoint** (commit only after approval)

Suggested: `git add scraper/log.py tests/test_log.py && git commit -m "feat(logs): stdout-default logger with env level/format and opt-in file (Factor XI)"`

---

## Task B2: MCP server log/status paths from settings

**Depends on:** A1, B1
**Files:**
- Modify: `mcp_server/server.py`
- Modify: `tests/test_status.py` (only if needed)

- [ ] **Step 1: Wire settings into `mcp_server/server.py`**

Add to imports:

```python
from scraper import settings
```

Replace the hardcoded paths (lines 38–39):

```python
_STATUS_PATH = Path(settings.STATUS_FILE)
_LOG_PATH: Path | None = Path(settings.LOG_FILE) if settings.LOG_FILE else None
```

In `get_scrape_status()`, guard the now-optional `_LOG_PATH` (replace the `if _LOG_PATH.exists():` block):

```python
    recent_logs: list[str] = []
    if _LOG_PATH is not None and _LOG_PATH.exists():
        try:
            lines = _LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
            recent_logs = lines[-30:]
        except OSError:
            pass
```

(Optional polish: pass `log_level=settings.LOG_LEVEL.lower()` to the `FastMCP(...)` constructor so FastMCP/uvicorn internal logging matches. Verify the accepted value form first — FastMCP exposes a `log_level` param.)

- [ ] **Step 2: Run status tests**

Run: `.venv/bin/python -m pytest tests/test_status.py -v`
Expected: pass. The recent-logs tests already `patch("mcp_server.server._LOG_PATH", <path>)`, which overrides the new `None` default; the no-file test returns before reading `_LOG_PATH`. If any assertion now fails because `_LOG_PATH` defaults to `None`, add `monkeypatch.setenv("LOG_FILE", str(tmp_path / "scraper.log"))` + reload, or keep the explicit `patch(...)` — do NOT weaken the assertions.

- [ ] **Step 3: Run full suite**

Run: `.venv/bin/python -m pytest -v`
Expected: no regressions

- [ ] **Step 4: Checkpoint** (commit only after approval)

Suggested: `git add mcp_server/server.py tests/test_status.py && git commit -m "refactor(logs): derive MCP log/status paths from settings"`

---

## Task B3: Route the stray CLI print through the logger

**Depends on:** B1
**Files:**
- Modify: `scraper/__main__.py`
- Create: `tests/test_main_cli.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_main_cli.py
from __future__ import annotations

from unittest.mock import patch

from scraper.__main__ import main


def test_bad_config_logs_error_and_returns_2():
    # Behavior: a bad config path is routed through the central logger (not print).
    # Mock get_logger in __main__'s namespace — deterministic, avoids capsys/caplog
    # gotchas (the job-scraper logger has propagate=False so caplog is blind, and its
    # StreamHandler binds stdout at init so capsys can miss it by test order).
    with patch("scraper.__main__.get_logger") as mock_get:
        rc = main(["-c", "does-not-exist.yaml"])
    assert rc == 2
    mock_get.return_value.error.assert_called_once()
    assert "config" in str(mock_get.return_value.error.call_args.args[0]).lower()
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/python -m pytest tests/test_main_cli.py -v`
Expected: FAIL — `__main__` does not import/call `get_logger` yet (it `print`s), so patching `scraper.__main__.get_logger` raises `AttributeError` until the logger change lands

- [ ] **Step 3: Update `scraper/__main__.py`**

Replace the `except ConfigError` print (line 46) with the logger; drop the now-unused `import sys` only if nothing else uses it (it is still used by `sys.argv` in `main`, so keep `import sys`).

```python
from .log import get_logger
```

```python
    try:
        config = load(args.config)
    except ConfigError as exc:
        get_logger().error("[config] %s", exc)
        return 2
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/bin/python -m pytest tests/test_main_cli.py -v`
Expected: pass
Run: `.venv/bin/python -m pytest -v`
Expected: no regressions

- [ ] **Step 5: Checkpoint** (commit only after approval)

Suggested: `git add scraper/__main__.py tests/test_main_cli.py && git commit -m "refactor(logs): route CLI config error through central logger"`

---

# PHASE C — Disposability (Python)

## Task C1: FastMCP lifespan closes Mongo on shutdown

**Depends on:** A2
**Files:**
- Modify: `mcp_server/server.py`
- Create: `tests/test_lifespan.py`

> ⚠️ **CORRECTED DURING EXECUTION (runtime e2e).** `FastMCP(lifespan=)` does accept the kwarg, but for the **streamable-http** transport it fires **per MCP session**, not at process shutdown — a SIGTERM e2e showed the lifespan logs never appeared. The shipped fix instead composes the **Starlette app's** lifespan (`app.router.lifespan_context`) in a `_build_app()` helper and runs uvicorn directly (mirroring `run_streamable_http_async`). The real implementation is in `mcp_server/server.py` (`_build_app`/`main`) and the test uses `starlette.testclient.TestClient` to drive the actual ASGI lifespan. The code blocks below are the original (superseded) approach — kept for history; see [[fastmcp-shutdown-lifespan]] for the corrected pattern.

- [ ] **Step 1: Write failing test**

```python
# tests/test_lifespan.py
from __future__ import annotations

import asyncio
from unittest.mock import patch


def test_lifespan_closes_mongo_on_exit():
    import mcp_server.server as server

    async def _run():
        async with server._lifespan(server.mcp):
            pass

    with patch.object(server.mongo, "close") as mock_close:
        asyncio.run(_run())
    mock_close.assert_called_once()
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/python -m pytest tests/test_lifespan.py -v`
Expected: `AttributeError: module 'mcp_server.server' has no attribute '_lifespan'`

- [ ] **Step 3: Add the lifespan in `mcp_server/server.py`**

Add imports:

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
```

Define the lifespan **above** the `mcp = FastMCP(...)` line, then wire it in:

```python
@asynccontextmanager
async def _lifespan(_server: FastMCP) -> AsyncIterator[None]:
    log = _get_logger()
    log.info("mcp server starting up")
    try:
        yield
    finally:
        log.info("mcp server shutting down; closing mongo client")
        mongo.close()


mcp = FastMCP("job-scraper", host=HOST, port=PORT, lifespan=_lifespan)
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/bin/python -m pytest tests/test_lifespan.py -v`
Expected: pass
Run: `.venv/bin/python -m pytest -v`
Expected: no regressions

- [ ] **Step 5: Manual smoke (disposability)** — confirm graceful shutdown logs

```bash
.venv/bin/python -m mcp_server.server &   # starts on :8080
sleep 2 && kill -TERM %1                   # SIGTERM
```
Expected: logs show "shutting down; closing mongo client" before exit. (Document the observation; `[VERIFIED]` once seen.)

- [ ] **Step 6: Checkpoint** (commit only after approval)

Suggested: `git add mcp_server/server.py tests/test_lifespan.py && git commit -m "feat(disposability): close mongo via FastMCP lifespan on shutdown"`

---

## Task C2: (folded into A4) Playwright browser-leak fix

The exception-path `browser.close()` fix lives in **Task A4 Step 5** (same file). If A4 is deferred, lift just that `try/finally` change into its own commit here:

- [ ] Apply the `try: ... finally: browser.close()` wrapper from A4 Step 5 to `scraper/fetchers/playwright.py`.
- [ ] Run `.venv/bin/python -m pytest -v` (no regressions; the change is exception-path only).
- [ ] Checkpoint — suggested: `git commit -m "fix(disposability): always close playwright browser on fetch failure"`

---

# PHASE D — Infra wiring + docs (Docker / compose / CI / docs)

> These edits are verified by build/run, not pytest. Build the images and run the dev stack after.

## Task D1: De-bake the cron schedule (runtime crontab)

**Files:**
- Modify: `cron/entrypoint.sh` (currently dead — Dockerfile calls supercronic directly)
- Modify: `cron/run-scraper.sh`
- Modify: `Dockerfile`

- [ ] **Step 1: Rewrite `cron/entrypoint.sh`** to generate the crontab at container start

```sh
#!/bin/sh
# Bot entrypoint: build the crontab at CONTAINER START (Factor IX disposability +
# runtime config) instead of baking it at image-build time. Precedence:
#   BOT_SCHEDULE env  >  .bot.schedule in /workspace/config.yaml  >  default.
# POSIX sh (bot /bin/sh is the node:20-slim shell). yq is installed in the image.
set -e

CONFIG=/workspace/config.yaml
CRONTAB=/workspace/scraper-bot/cron/scraper-crontab
DEFAULT_SCHEDULE="0 11 * * *"

SCHEDULE="${BOT_SCHEDULE:-}"
if [ -z "$SCHEDULE" ] && [ -f "$CONFIG" ]; then
  SCHEDULE="$(yq -r '.bot.schedule // ""' "$CONFIG" 2>/dev/null || true)"
fi
[ -n "$SCHEDULE" ] || SCHEDULE="$DEFAULT_SCHEDULE"

echo "[entrypoint] cron schedule: $SCHEDULE"
printf '%s /bin/sh /workspace/scraper-bot/cron/run-scraper.sh\n' "$SCHEDULE" > "$CRONTAB"

exec /usr/local/bin/supercronic "$CRONTAB"
```

- [ ] **Step 2: Update `cron/run-scraper.sh`** — model from env/config, stdout-default logging

```sh
#!/bin/sh
# Cron job: run claude-code with the markdown prompt.
# Logs stream to STDOUT (supercronic -> `docker logs`, Factor XI). Set BOT_LOG_FILE
# to ALSO append to a file. Model precedence: CLAUDE_MODEL > config.yaml bot.model > default.
PROMPT=/workspace/scraper-bot/prompts/scrape-and-post.md
CONFIG=/workspace/config.yaml
DEFAULT_MODEL="claude-haiku-4-5-20251001"

MODEL="${CLAUDE_MODEL:-}"
if [ -z "$MODEL" ] && [ -f "$CONFIG" ]; then
  MODEL="$(yq -r '.bot.model // ""' "$CONFIG" 2>/dev/null || true)"
fi
[ -n "$MODEL" ] || MODEL="$DEFAULT_MODEL"

cd /workspace/scraper-bot
echo "[$(date)] starting multi-site scraper run (model=$MODEL)..."

run_claude() {
  # --dangerously-skip-permissions: unattended cron, no TTY to approve prompts.
  # --verbose --output-format stream-json: one JSON event per step (streams live).
  claude \
    --model "$MODEL" \
    --dangerously-skip-permissions \
    --verbose \
    --output-format stream-json \
    -p "$(cat "$PROMPT")" \
    2>&1
}

if [ -n "${BOT_LOG_FILE:-}" ]; then
  # capture claude's rc (not tee's) through a temp file — POSIX sh has no PIPESTATUS
  { run_claude; echo "$?" >/tmp/claude.rc; } | tee -a "$BOT_LOG_FILE"
  EXIT_CODE="$(cat /tmp/claude.rc)"; rm -f /tmp/claude.rc
else
  run_claude
  EXIT_CODE=$?
fi

if [ "$EXIT_CODE" -ne 0 ]; then
  echo "[$(date)] ERROR: claude exited with code $EXIT_CODE" >&2
fi
echo "[$(date)] run complete."
```

- [ ] **Step 3: Update the `Dockerfile` bot stage**

Replace the crontab-baking `RUN` (lines 93–100) with one that no longer generates the crontab (entrypoint does it now) but keeps perms + claude dirs:

```dockerfile
RUN chmod +x cron/entrypoint.sh cron/run-scraper.sh \
 && mkdir -p /home/node/.claude \
 && touch /home/node/.claude.json \
 && chown -R node:node /home/node /workspace
```

Replace ENTRYPOINT/CMD (lines 104–105):

```dockerfile
ENTRYPOINT ["/workspace/scraper-bot/cron/entrypoint.sh"]
CMD []
```

- [ ] **Step 4: Verify (build + dev idle + manual fire)**

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile bot up --build -d
# dev overrides entrypoint to `sleep infinity`, so generate+inspect crontab manually:
docker exec job-scraper-bot sh -lc 'BOT_SCHEDULE="*/5 * * * *" /workspace/scraper-bot/cron/entrypoint.sh & sleep 1; cat /workspace/scraper-bot/cron/scraper-crontab'
```
Expected: crontab line shows `*/5 * * * * /bin/sh .../run-scraper.sh`. (Confirms env-driven schedule with no rebuild.)

- [ ] **Step 5: Checkpoint** (commit only after approval)

Suggested: `git add cron/entrypoint.sh cron/run-scraper.sh Dockerfile && git commit -m "feat(config): generate cron schedule at container start (no rebuild); model via env/config"`

---

## Task D2: Compose env wiring + disposability hardening

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.dev.yml`
- Modify: `docker-compose.prod.yml` (confirm only)

- [ ] **Step 1: `docker-compose.yml` — scraper-mcp**: add logging env + `init`/`stop_grace_period`

Add under `scraper-mcp:` (alongside existing keys):

```yaml
    init: true            # tini reaps playwright/chromium subprocesses (Factor IX)
    stop_grace_period: 20s
```

Add to `scraper-mcp.environment` (after the MONGO_* lines):

```yaml
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - LOG_FORMAT=${LOG_FORMAT:-plain}
      - LOG_FILE=${LOG_FILE:-}
```

- [ ] **Step 2: `docker-compose.yml` — bot**: add schedule/model/log env + hardening

Add under `bot:`:

```yaml
    init: true
    stop_grace_period: 30s
```

Add to `bot.environment`:

```yaml
      - BOT_SCHEDULE=${BOT_SCHEDULE:-}
      - CLAUDE_MODEL=${CLAUDE_MODEL:-}
      - BOT_LOG_FILE=${BOT_LOG_FILE:-}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - LOG_FORMAT=${LOG_FORMAT:-plain}
```

- [ ] **Step 3: `docker-compose.yml` — mongo**: add grace period

```yaml
    stop_grace_period: 30s
```

- [ ] **Step 4: `docker-compose.dev.yml`** — dev gets DEBUG + a file (so `recent_logs` works locally)

Add a `scraper-mcp` env override (merged over base):

```yaml
  scraper-mcp:
    environment:
      - LOG_LEVEL=DEBUG
      - LOG_FILE=/app/logs/scraper.log
    volumes:
      - /tmp/config.dev.yaml:/app/config.yaml
```

(Keep the existing `bot` override as-is — `sleep infinity` for idle dev.)

- [ ] **Step 5: `docker-compose.prod.yml`** — confirm no extra change needed

Prod inherits the base env defaults (INFO/plain, no file, no `BOT_SCHEDULE` → falls back to baked `config.yaml`). No edit required unless you want prod to set `BOT_SCHEDULE`/`LOG_*` — those flow from `deploy.yml` (Task D3). Document the decision in the PR.

- [ ] **Step 6: Verify**

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile mcp config | grep -A2 -i "LOG_\|init\|stop_grace"
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile mcp up --build -d
docker logs job-scraper-mcp | tail -20    # expect single-stream startup logs at DEBUG
curl -fsS localhost:8080/health
```

- [ ] **Step 7: Checkpoint** (commit only after approval)

Suggested: `git add docker-compose.yml docker-compose.dev.yml docker-compose.prod.yml && git commit -m "feat(disposability,logs): compose env wiring + init/stop_grace hardening"`

---

## Task D3: CI deploy env injection

**Files:**
- Modify: `.github/workflows/deploy.yml`

- [ ] **Step 1: `deploy-mcp`** — pass logging vars

Extend the `envs:` list (line ~126):

```yaml
          envs: MCP_IMAGE,MONGO_ROOT_USER,MONGO_ROOT_PASSWORD,MONGO_DB_NAME,MONGO_COLLECTION_NAME,LOG_LEVEL,LOG_FORMAT
```

Add to the step `env:` (line ~138):

```yaml
          LOG_LEVEL: ${{ vars.LOG_LEVEL || 'INFO' }}
          LOG_FORMAT: ${{ vars.LOG_FORMAT || 'plain' }}
```

- [ ] **Step 2: `deploy-bot`** — pass schedule/model

Extend the `envs:` list (line ~175):

```yaml
          envs: BOT_IMAGE,DISCORD_BOT_TOKEN,DISCORD_CHANNEL_ID,CLAUDE_CONFIG_DIR,CLAUDE_CONFIG_FILE,TZ,BOT_SCHEDULE,CLAUDE_MODEL
```

Add to the step `env:` (line ~187):

```yaml
          BOT_SCHEDULE: ${{ vars.BOT_SCHEDULE }}
          CLAUDE_MODEL: ${{ vars.CLAUDE_MODEL }}
```

(These are GitHub **Variables** with empty defaults → bot falls back to baked `config.yaml`. Setting `vars.BOT_SCHEDULE` in repo settings now changes the schedule on next deploy with no code change/rebuild.)

- [ ] **Step 3: Verify (lint the YAML)**

```bash
yq '.jobs."deploy-bot".steps[] | select(.name=="Deploy scraper-bot") | .env' .github/workflows/deploy.yml
```
Expected: shows `BOT_SCHEDULE`, `CLAUDE_MODEL`.

- [ ] **Step 4: Checkpoint** (commit only after approval)

Suggested: `git add .github/workflows/deploy.yml && git commit -m "ci: inject schedule/model/log env into prod deploy"`

---

## Task D4: Document the central config contract

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/configuration.md`

- [ ] **Step 1: `.env.example`** — add the new optional knobs (after the existing block)

```bash
# --- Logging (all optional; apply to scraper-mcp) -------------------------------
# LOG_LEVEL: DEBUG|INFO|WARNING|ERROR  (default INFO)
# LOG_FORMAT: plain|json               (default plain)
# LOG_FILE: path to ALSO write a rotating file (default: stdout only)
LOG_LEVEL=
LOG_FORMAT=
LOG_FILE=

# --- Bot (all optional) --------------------------------------------------------
# BOT_SCHEDULE: cron expr; overrides config.yaml bot.schedule WITHOUT a rebuild
# CLAUDE_MODEL: overrides config.yaml bot.model
# BOT_LOG_FILE: path to ALSO append the cron run log (default: stdout only)
BOT_SCHEDULE=
CLAUDE_MODEL=
BOT_LOG_FILE=
```

- [ ] **Step 2: `README.md`** — update three things

  - In "Config: config.yaml + the dev patch": replace the `> Note on bot.schedule` block (it says a rebuild is required) with: schedule now reads `BOT_SCHEDULE` env at container start (falls back to `config.yaml` `bot.schedule`), so changing it needs only a container restart / redeploy var — no rebuild. Same pattern for `bot.model` via `CLAUDE_MODEL`.
  - In "Check logs": note logs are a single stdout stream by default (`docker logs`), tunable via `LOG_LEVEL`/`LOG_FORMAT`, and that `LOG_FILE`/`BOT_LOG_FILE` opt back into files.
  - Add a short "Config layers" note pointing at the three-layer table (settings.py / config.yaml / config.py).

- [ ] **Step 3: `docs/configuration.md`** — add the full env-var contract table (name, default, component, effect) for: `MONGO_*`, `LOG_LEVEL`, `LOG_FORMAT`, `LOG_FILE`, `LOG_FILE_MAX_BYTES`, `LOG_FILE_BACKUP_COUNT`, `STATUS_FILE`, `MCP_HOST`, `MCP_PORT`, `SCRAPER_CONFIG`, `PROXY_TEST_*`, `BOT_SCHEDULE`, `CLAUDE_MODEL`, `BOT_LOG_FILE`, `TZ`, `CLAUDE_CONFIG_*`, `DISCORD_*`, `MONGO_ROOT_*`; plus the new `config.yaml` `timeouts:` + `bot.model` schema.

- [ ] **Step 4: Checkpoint** (commit only after approval)

Suggested: `git add .env.example README.md docs/configuration.md && git commit -m "docs: document central env contract, schedule/model/log knobs"`

---

## Final verification (run before opening the PR)

- [ ] `.venv/bin/python -m pytest -v` — full suite green
- [ ] `pre-commit run --all-files` — ruff + mypy clean
- [ ] `docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile mcp up --build -d` then `curl -fsS localhost:8080/health` → `{"status":"ok"...}`
- [ ] `docker logs job-scraper-mcp` shows a single stdout stream at the configured level; SIGTERM (`docker compose ... stop scraper-mcp`) logs the lifespan shutdown line
- [ ] Bot: `BOT_SCHEDULE` env produces the expected crontab line at container start (Task D1 Step 4)
- [ ] TUI still starts and the dev merge still produces `/tmp/config.dev.yaml` (`python scripts/manage.py`)

---

## Self-Review

**Spec coverage (vs the user's goal — config/logs/disposability, centralized & 12-factor):**
- Config in environment (III): `scraper/settings.py` centralizes + dedupes `MONGO_*` (A1–A2); env contract documented (D4). ✅
- Centralized files: timeouts + model → `config.yaml` (A3–A4); three-layer table documents where each knob lives. ✅
- Logs as streams (XI): stdout default, env level/format, opt-in file (B1–B2); stray `print` routed (B3); bot tees only on opt-in (D1). ✅
- Disposability (IX): Mongo `close()` + FastMCP lifespan (A2, C1); Playwright leak fix (A4/C2); `_location` client closed (A2); compose `init`/`stop_grace_period` (D2). ✅
- De-bake schedule: runtime crontab from `BOT_SCHEDULE` (D1), wired through compose + CI (D2–D3). ✅

**Placeholder scan:** No TBD/TODO/"handle edge cases" — every code step shows complete code or an exact before/after anchor.

**Type consistency:** `FetchTuning` defined once in `scraper/config.py`, imported by `config_loader`, fetchers, `sites/base`, `runner`. `tuning` kwarg name + `_tuning`/`self.tuning` attribute names are consistent across A4. `mongo.close()` signature matches its test (A2) and lifespan call (C1). `settings.*` attribute names match across `mongo.py`, `_location.py`, `log.py`, `server.py`, and tests. `_LOG_PATH: Path | None` guarded everywhere it is read.

**Known verification debt to close during execution:**
- FastMCP `lifespan` kwarg — verified present via `inspect`. The `log_level` polish in B2 is optional; verify the accepted value form before adding.
- Playwright leak fix is exception-path only; covered by manual reasoning, not a unit test (Playwright not exercised in CI).
