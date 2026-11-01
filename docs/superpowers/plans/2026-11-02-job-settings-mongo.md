# Job Settings in Mongo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Run every command from the `scraper/` repo root unless a step says otherwise

**Goal:** Move the job settings from `config.yaml` into a new Mongo collection, so `/config` can edit them on localhost and in prod with no rebuild

**Architecture:** One document per environment lives in `job_settings` on that host's own Mongo, and `job_settings_history` keeps the last 20 versions. Only `scraper-mcp` and the `scraper` CLI touch these collections. The UI saves through MCP tools, so the public UI container gets no DB password. Saves use a version check, and validation stays in `scraper/config_loader.py`

**Tech Stack:** Python 3.12, pymongo 4, FastMCP, FastAPI, pydantic, mongomock (tests), Vue 3, Pinia, Vitest, Docker Compose, GitHub Actions

---

## Agreed decisions

These came from the grilling session on 2026-11-02. Do not reopen them while building

- Mongo is the only source for job settings. Moved keys: `keywords`, `limit`, `max_age_hours`, `filter`, `default_fields`, `sites`
- `config.yaml` keeps `concurrency`, `output_dir`, and `bot`
- Proxy moves to env var `SCRAPER_PROXY_URL`. Unset is an error, empty means direct connection
- `config.dev.patch.yaml`, the `yq` merge, `/tmp/config.dev.yaml`, locked fields, and file backups all go away
- Prod `/config` becomes editable behind the existing login
- If Mongo is down or the document is missing, `scrape_jobs` returns `ok: false` with a clear reason
- `seed.sh` loads one committed seed file and only inserts when the document is missing
- `/config` edits everything except `url_template`, and has no Proxy URL field
- `/config` can restore any of the last 20 versions
- Overlapping saves fail with a reload message
- The CLI reads Mongo. `--keyword` and site args still override

## Patch rules

`update_config` used a deep merge. That cannot express two things the page needs: replacing a site filter, and returning a site field to the global value. The new merge rule is

- Top-level keys are replaced whole
- `sites` merges by site name
- Each site's fields are replaced whole, so `filter` and `api` are replaced whole
- `None` removes the key, so a site field returns to the global value

A site with `filter: {}` has no filter. A site with no `filter` key uses the global filter. Upwork depends on this

## Known limits

- MCP tools run on the event loop and `scrape_jobs` blocks it. During a scrape `get_config` times out, the page shows stale data, and saving is off until the scrape ends. This matches how the page already behaves
- Mongo here is a single node with no transactions. The settings update runs first and the history insert runs second. A crash between them loses one history entry and nothing else

## File map

**Create**

| File | Job |
|---|---|
| `scraper/job_settings.py` | `JobSettingsStore`, `merge_settings`, `load_app_config`, `open_store` |
| `scraper/seed_settings.py` | Seed command |
| `seeds/job_settings.yaml` | Committed first version of the settings |
| `tests/test_config_loader.py` | Parser, machine settings, proxy env tests |
| `tests/test_job_settings.py` | Store and merge tests |
| `tests/test_seed_settings.py` | Seed tests |
| `tests/test_config_tools.py` | MCP tool tests |
| `tests/test_cli.py` | CLI tests |
| `ui/src/modules/config/domain/usecases/GetConfigHistoryUseCase.ts` | History use case |
| `ui/src/modules/config/domain/usecases/RestoreConfigUseCase.ts` | Restore use case |
| `ui/src/modules/config/presentation/components/ListInput.vue` | Comma list input |
| `ui/src/modules/config/presentation/components/LineListInput.vue` | One-per-line list input, for values that hold commas |
| `ui/src/modules/config/presentation/components/FilterFields.vue` | Filter inputs |
| `ui/src/modules/config/presentation/components/SiteSettings.vue` | One site's settings |
| `ui/src/modules/config/presentation/components/ConfigHistory.vue` | Version list with restore |

**Modify**

`scraper/config_loader.py`, `scraper/__main__.py`, `scraper/__init__.py`, `mcp_server/mongo.py`, `mcp_server/server.py`, `ui_server/errors.py`, `ui_server/settings.py`, `ui_server/app.py`, `ui_server/dependencies.py`, `ui_server/requirements.txt`, `ui_server/routes/config.py`, `ui_server/schema/config.py`, `ui_server/services/mcp_gateway.py`, the `ui/src/modules/config` module, `config.yaml`, `requirements.txt`, `seed.sh`, `Dockerfile`, `docker-compose.yml`, `docker-compose.dev.yml`, `.env.example`, `.gitignore`, `.github/workflows/deploy.yml`, `prompts/scrape-and-post.md`, `scripts/run_dev.sh`, `scripts/run_prod.sh`, `scripts/test-locally.sh`, `scripts/test_cron_dev.sh`, `scripts/environments.yaml`, `scripts/manage.py`, `scripts/manage_tui/`, docs, and the listed tests

**Delete**

`ui_server/services/config_store.py`, `tests/test_ui_config_store.py`, `config.dev.patch.yaml`, `config.dev.patch.yaml.example`, `config-backups/`

---

## Task 0: Prepare the branch

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Handle the uncommitted work**

`git status` shows edits in `config.dev.patch.yaml`, `scripts/manage.py`, `scripts/manage_tui/__init__.py`, and `scripts/ssh-tunnel.sh.example`. Tasks 12 and 13 touch the first three. Ask the owner to commit or park them. Do not discard them

- [ ] **Step 2: Create the branch from the current tip**

The UI already depends on `save_run`, which lives on `feat/scrape-save-run-option`, so branch from there

```bash
git switch -c feat/job-settings-mongo
```

- [ ] **Step 3: Add mongomock**

In `requirements.txt`, add this line right after `pytest>=8.0`

```text
mongomock>=4.3
```

```bash
uv pip install --python .venv/bin/python mongomock
```

- [ ] **Step 4: Check the baseline**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add requirements.txt
git commit -m "chore: add mongomock for store tests"
```

---

## Task 1: Split the parser from the file loader

**Files:**
- Modify: `scraper/config_loader.py`
- Test: `tests/test_config_loader.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_loader.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from scraper.config_loader import (
    PROXY_ENV_VAR,
    ConfigError,
    parse,
    read_machine_settings,
    resolve_proxy_url,
    validate_job_settings,
)

SETTINGS = {
    "keywords": ["devops"],
    "limit": 3,
    "sites": {"jobstreet": {"url_template": "https://id.jobstreet.com/id/{keyword_slug}-jobs"}},
}


def test_parse_builds_config_with_proxy():
    config = parse({**SETTINGS, "concurrency": 4}, "socks5://localhost:1080")

    assert config.keywords == ("devops",)
    assert config.concurrency == 4
    assert config.proxy is not None
    assert config.proxy.url == "socks5://localhost:1080"


def test_parse_without_proxy():
    assert parse(SETTINGS, None).proxy is None


def test_read_machine_settings_reads_mapping(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("concurrency: 5\n")

    assert read_machine_settings(path) == {"concurrency": 5}


def test_read_machine_settings_requires_file(tmp_path: Path):
    with pytest.raises(ConfigError, match="config file not found"):
        read_machine_settings(tmp_path / "missing.yaml")


def test_resolve_proxy_url_rejects_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(PROXY_ENV_VAR, raising=False)

    with pytest.raises(ConfigError, match=PROXY_ENV_VAR):
        resolve_proxy_url()


def test_resolve_proxy_url_treats_empty_as_direct(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(PROXY_ENV_VAR, "  ")

    assert resolve_proxy_url() is None


def test_resolve_proxy_url_returns_value(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(PROXY_ENV_VAR, " socks5://localhost:1080 ")

    assert resolve_proxy_url() == "socks5://localhost:1080"


def test_validate_job_settings_accepts_valid_settings():
    validate_job_settings(SETTINGS)


def test_validate_job_settings_rejects_machine_keys():
    with pytest.raises(ConfigError, match="not a job setting: proxy"):
        validate_job_settings({**SETTINGS, "proxy": "socks5://localhost:1080"})


def test_validate_job_settings_rejects_bad_values():
    with pytest.raises(ConfigError, match="'limit' must be >= 1"):
        validate_job_settings({**SETTINGS, "limit": 0})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config_loader.py -q`
Expected: FAIL with `ImportError: cannot import name 'PROXY_ENV_VAR'`

- [ ] **Step 3: Add the constants**

In `scraper/config_loader.py`, change the imports and add the constants after `ALLOWED_URL_HOSTS`

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
```

```python
PROXY_ENV_VAR = "SCRAPER_PROXY_URL"

JOB_SETTINGS_KEYS: frozenset[str] = frozenset(
    {"keywords", "limit", "max_age_hours", "filter", "default_fields", "sites"}
)
```

- [ ] **Step 4: Split `load`**

Replace the first lines of `load`

```python
def load(path: Path) -> AppConfig:
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")

    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"config root must be a mapping, got {type(raw).__name__}")

    keywords = _resolve_keywords(raw)
```

with

```python
def read_machine_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")

    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"config root must be a mapping, got {type(raw).__name__}")
    return raw


def resolve_proxy_url() -> str | None:
    value = os.environ.get(PROXY_ENV_VAR)
    if value is None:
        raise ConfigError(
            f"{PROXY_ENV_VAR} is not set. "
            "Set it to a proxy URL, or to empty for a direct connection"
        )
    return value.strip() or None


def validate_job_settings(settings: dict[str, Any]) -> None:
    unknown = sorted(set(settings) - JOB_SETTINGS_KEYS)
    if unknown:
        raise ConfigError(f"not a job setting: {', '.join(unknown)}")
    parse(settings, None)


def load(path: Path) -> AppConfig:
    raw = read_machine_settings(path)
    proxy = raw.get("proxy")
    return parse(raw, proxy if isinstance(proxy, str) else None)


def parse(raw: dict[str, Any], proxy_url: str | None) -> AppConfig:
    keywords = _resolve_keywords(raw)
```

`load` stays for now because `mcp_server/server.py`, `scraper/__main__.py`, and `ui_server/services/config_store.py` still call it. Task 7 removes it

- [ ] **Step 5: Take the proxy from the argument**

Replace

```python
    proxy: ProxyConfig | None = None
    proxy_url = raw.get("proxy")
    if isinstance(proxy_url, str) and proxy_url.strip():
        proxy = ProxyConfig(url=proxy_url.strip())
```

with

```python
    proxy: ProxyConfig | None = None
    if proxy_url and proxy_url.strip():
        proxy = ProxyConfig(url=proxy_url.strip())
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_config_loader.py tests/test_config_api.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add scraper/config_loader.py tests/test_config_loader.py
git commit -m "refactor: split config parsing from the config file"
```

---

## Task 2: Add the job settings store

**Files:**
- Create: `scraper/job_settings.py`
- Test: `tests/test_job_settings.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_job_settings.py`

```python
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import mongomock
import pytest
from pymongo.errors import ServerSelectionTimeoutError

from scraper.config_loader import PROXY_ENV_VAR, ConfigError
from scraper.job_settings import (
    KEEP_HISTORY,
    JobSettingsStore,
    SettingsConflictError,
    SettingsMissingError,
    SettingsUnavailableError,
    load_app_config,
    merge_settings,
)

UPWORK_URL = "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency"
SETTINGS: dict[str, Any] = {
    "keywords": ["devops"],
    "limit": 3,
    "max_age_hours": 72,
    "filter": {"location": ["jakarta"]},
    "sites": {
        "upwork": {"enabled": True, "limit": 30, "filter": {}, "url_template": UPWORK_URL},
        "glints": {
            "enabled": False,
            "limit": 2,
            "url_template": "https://glints.com/id/opportunities/jobs/explore?keyword={keyword}",
        },
    },
}


@pytest.fixture
def store() -> JobSettingsStore:
    job_store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])
    assert job_store.seed(deepcopy(SETTINGS)) is True
    return job_store


def test_merge_replaces_top_level_keys():
    merged = merge_settings(SETTINGS, {"filter": {"work_type": ["remote"]}})

    assert merged["filter"] == {"work_type": ["remote"]}
    assert merged["keywords"] == ["devops"]


def test_merge_changes_one_site_and_keeps_the_rest():
    merged = merge_settings(SETTINGS, {"sites": {"upwork": {"limit": 9}}})

    assert merged["sites"]["upwork"]["limit"] == 9
    assert merged["sites"]["upwork"]["url_template"] == UPWORK_URL
    assert merged["sites"]["glints"] == SETTINGS["sites"]["glints"]


def test_merge_replaces_site_filter_with_empty_filter():
    merged = merge_settings(SETTINGS, {"sites": {"glints": {"filter": {}}}})

    assert merged["sites"]["glints"]["filter"] == {}


def test_merge_removes_site_field_on_none():
    merged = merge_settings(SETTINGS, {"sites": {"upwork": {"filter": None}}})

    assert "filter" not in merged["sites"]["upwork"]


def test_merge_does_not_change_input():
    original = deepcopy(SETTINGS)

    merge_settings(SETTINGS, {"limit": 9, "sites": {"upwork": {"limit": 1}}})

    assert SETTINGS == original


def test_merge_rejects_site_that_is_not_a_mapping():
    with pytest.raises(ConfigError, match="sites.upwork must be a mapping"):
        merge_settings(SETTINGS, {"sites": {"upwork": 3}})


def test_read_returns_seeded_settings(store: JobSettingsStore):
    stored = store.read()

    assert stored.version == 1
    assert stored.updated_by == "seed"
    assert stored.settings["keywords"] == ["devops"]


def test_read_reports_missing_document():
    store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])

    with pytest.raises(SettingsMissingError, match="seed.sh job-settings"):
        store.read()


def test_seed_keeps_existing_document(store: JobSettingsStore):
    store.save({"limit": 9}, 1, "ui")

    assert store.seed(deepcopy(SETTINGS)) is False
    assert store.read().settings["limit"] == 9


def test_seed_rejects_invalid_settings():
    store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])

    with pytest.raises(ConfigError):
        store.seed({"keywords": []})


def test_save_moves_to_next_version_and_keeps_old_one(store: JobSettingsStore):
    saved = store.save({"limit": 9}, 1, "ui")

    assert saved.version == 2
    assert saved.updated_by == "ui"
    assert store.read().settings["limit"] == 9
    history = store.history()
    assert [entry.version for entry in history] == [1]
    assert history[0].settings["limit"] == 3


def test_save_rejects_stale_version(store: JobSettingsStore):
    store.save({"limit": 9}, 1, "ui")

    with pytest.raises(SettingsConflictError):
        store.save({"limit": 10}, 1, "ui")

    assert store.read().settings["limit"] == 9


def test_save_detects_a_write_between_read_and_update(
    store: JobSettingsStore, monkeypatch: pytest.MonkeyPatch
):
    stale = store.read()
    store.save({"limit": 9}, None, "ui")
    monkeypatch.setattr(store, "read", lambda: stale)

    with pytest.raises(SettingsConflictError):
        store.save({"limit": 10}, None, "ui")


def test_save_leaves_document_unchanged_when_invalid(store: JobSettingsStore):
    with pytest.raises(ConfigError):
        store.save({"limit": 0}, 1, "ui")

    assert store.read().version == 1
    assert store.history() == ()


def test_history_keeps_newest_versions(store: JobSettingsStore):
    for limit in range(1, KEEP_HISTORY + 4):
        store.save({"limit": limit}, None, "ui")

    versions = [entry.version for entry in store.history()]

    assert len(versions) == KEEP_HISTORY
    assert versions[0] == KEEP_HISTORY + 3
    assert versions == sorted(versions, reverse=True)


def test_restore_brings_back_settings_as_new_version(store: JobSettingsStore):
    store.save({"limit": 9}, 1, "ui")

    restored = store.restore(1, 2, "ui")

    assert restored.version == 3
    assert store.read().settings["limit"] == 3
    assert [entry.version for entry in store.history()] == [2, 1]


def test_restore_rejects_unknown_version(store: JobSettingsStore):
    with pytest.raises(ConfigError, match="no saved version 8"):
        store.restore(8, 1, "ui")


def test_mongo_failure_hides_connection_details():
    database = MagicMock()
    database.__getitem__.return_value.find_one.side_effect = ServerSelectionTimeoutError(
        "secret-host:27017"
    )

    with pytest.raises(SettingsUnavailableError) as caught:
        JobSettingsStore(database).read()

    assert "secret-host" not in str(caught.value)


def test_load_app_config_joins_file_store_and_proxy(
    store: JobSettingsStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "config.yaml"
    path.write_text("concurrency: 5\n")
    monkeypatch.setenv(PROXY_ENV_VAR, "socks5://localhost:1080")

    config = load_app_config(path, store)

    assert config.concurrency == 5
    assert config.keywords == ("devops",)
    assert config.proxy is not None
    assert config.proxy.url == "socks5://localhost:1080"
    assert config.filter_for("upwork") == {}


def test_load_app_config_stops_when_proxy_is_unset(
    store: JobSettingsStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "config.yaml"
    path.write_text("concurrency: 5\n")
    monkeypatch.delenv(PROXY_ENV_VAR, raising=False)

    with pytest.raises(ConfigError, match=PROXY_ENV_VAR):
        load_app_config(path, store)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_job_settings.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.job_settings'`

- [ ] **Step 3: Write the store**

Create `scraper/job_settings.py`

```python
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pymongo import DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from .config_loader import (
    AppConfig,
    ConfigError,
    parse,
    read_machine_settings,
    resolve_proxy_url,
    validate_job_settings,
)

SETTINGS_COLLECTION = "job_settings"
HISTORY_COLLECTION = "job_settings_history"
SETTINGS_ID = "active"
KEEP_HISTORY = 20
SOURCE_SEED = "seed"
FIRST_VERSION = 1
CONFLICT_MESSAGE = "These settings changed somewhere else. Reload and try again"


class SettingsMissingError(ConfigError):
    pass


class SettingsConflictError(ConfigError):
    pass


class SettingsUnavailableError(ConfigError):
    pass


@dataclass(frozen=True)
class StoredSettings:
    version: int
    settings: dict[str, Any]
    updated_at: str
    updated_by: str


def _to_stored(document: dict[str, Any]) -> StoredSettings:
    return StoredSettings(
        version=document["version"],
        settings=document["settings"],
        updated_at=document["updated_at"],
        updated_by=document["updated_by"],
    )


def _stamp(settings: dict[str, Any], version: int, source: str) -> dict[str, Any]:
    return {
        "version": version,
        "settings": settings,
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": source,
    }


def _apply_fields(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    kept = {key: value for key, value in current.items() if key not in patch}
    changed = {key: value for key, value in patch.items() if value is not None}
    return {**kept, **changed}


def _merge_site(current: dict[str, Any], name: str, patch: Any) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise ConfigError(f"sites.{name} must be a mapping")
    return _apply_fields(current.get(name, {}), patch)


def merge_settings(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = _apply_fields(current, {k: v for k, v in patch.items() if k != "sites"})
    site_patches = patch.get("sites")
    if site_patches is None:
        return merged
    if not isinstance(site_patches, dict):
        raise ConfigError("'sites' must be a mapping")
    sites = current.get("sites", {})
    changed = {name: _merge_site(sites, name, fields) for name, fields in site_patches.items()}
    return {**merged, "sites": {**sites, **changed}}


@contextmanager
def _mongo_errors() -> Iterator[None]:
    try:
        yield
    except PyMongoError as exc:
        # Keep the message short: pymongo errors can name hosts
        raise SettingsUnavailableError(
            f"The job settings store cannot be reached ({type(exc).__name__})"
        ) from exc


class JobSettingsStore:
    def __init__(self, database: Any) -> None:
        self._settings = database[SETTINGS_COLLECTION]
        self._history = database[HISTORY_COLLECTION]

    def read(self) -> StoredSettings:
        with _mongo_errors():
            document = self._settings.find_one({"_id": SETTINGS_ID})
        if document is None:
            raise SettingsMissingError(
                "Job settings are missing. Run ./seed.sh job-settings for this environment"
            )
        return _to_stored(document)

    def seed(self, settings: dict[str, Any]) -> bool:
        validate_job_settings(settings)
        document = {"_id": SETTINGS_ID, **_stamp(settings, FIRST_VERSION, SOURCE_SEED)}
        with _mongo_errors():
            try:
                self._settings.insert_one(document)
            except DuplicateKeyError:
                return False
        return True

    def save(
        self, patch: dict[str, Any], expected_version: int | None, source: str
    ) -> StoredSettings:
        current = self._read_expected(expected_version)
        return self._replace(current, merge_settings(current.settings, patch), source)

    def restore(self, version: int, expected_version: int, source: str) -> StoredSettings:
        current = self._read_expected(expected_version)
        with _mongo_errors():
            entry = self._history.find_one({"version": version})
        if entry is None:
            raise ConfigError(f"no saved version {version}")
        return self._replace(current, entry["settings"], source)

    def history(self) -> tuple[StoredSettings, ...]:
        with _mongo_errors():
            documents = list(self._history.find().sort("version", DESCENDING).limit(KEEP_HISTORY))
        return tuple(_to_stored(document) for document in documents)

    def _read_expected(self, expected_version: int | None) -> StoredSettings:
        current = self.read()
        if expected_version is not None and expected_version != current.version:
            raise SettingsConflictError(CONFLICT_MESSAGE)
        return current

    def _replace(
        self, current: StoredSettings, settings: dict[str, Any], source: str
    ) -> StoredSettings:
        validate_job_settings(settings)
        fields = _stamp(settings, current.version + 1, source)
        with _mongo_errors():
            previous = self._settings.find_one_and_update(
                {"_id": SETTINGS_ID, "version": current.version},
                {"$set": fields},
                return_document=ReturnDocument.BEFORE,
            )
            if previous is None:
                raise SettingsConflictError(CONFLICT_MESSAGE)
            self._keep_history(previous)
        return _to_stored(fields)

    def _keep_history(self, previous: dict[str, Any]) -> None:
        self._history.insert_one({k: v for k, v in previous.items() if k != "_id"})
        stale = self._history.find({}, {"_id": 1}).sort("version", DESCENDING).skip(KEEP_HISTORY)
        stale_ids = [document["_id"] for document in stale]
        if stale_ids:
            self._history.delete_many({"_id": {"$in": stale_ids}})


def open_store() -> JobSettingsStore:
    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB_NAME", "job_scraper")
    timeout = int(os.environ.get("MONGO_SERVER_SELECTION_TIMEOUT_MS", "3000"))
    return JobSettingsStore(MongoClient(uri, serverSelectionTimeoutMS=timeout)[db_name])


def load_app_config(path: Path, store: JobSettingsStore) -> AppConfig:
    machine = read_machine_settings(path)
    return parse({**machine, **store.read().settings}, resolve_proxy_url())
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_job_settings.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scraper/job_settings.py tests/test_job_settings.py
git commit -m "feat: add Mongo store for job settings"
```

---

## Task 3: Add the seed file and seed command

**Files:**
- Create: `seeds/job_settings.yaml`, `scraper/seed_settings.py`
- Modify: `seed.sh`
- Test: `tests/test_seed_settings.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_seed_settings.py`

```python
from __future__ import annotations

from pathlib import Path

import mongomock
import pytest
import yaml

from scraper import seed_settings
from scraper.config_loader import validate_job_settings
from scraper.job_settings import JobSettingsStore

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = REPO_ROOT / "seeds" / "job_settings.yaml"
SMALL_SEED = """
keywords: [devops]
sites:
  upwork:
    url_template: "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency"
"""


def _store() -> JobSettingsStore:
    return JobSettingsStore(mongomock.MongoClient()["job_scraper"])


def test_committed_seed_file_is_valid():
    validate_job_settings(yaml.safe_load(SEED_PATH.read_text()))


def test_committed_seed_file_keeps_upwork_location_filter_off():
    settings = yaml.safe_load(SEED_PATH.read_text())

    assert settings["sites"]["upwork"]["filter"] == {}


def test_seed_file_inserts_once(tmp_path: Path):
    path = tmp_path / "seed.yaml"
    path.write_text(SMALL_SEED)
    store = _store()

    assert seed_settings.seed_file(path, store) is True
    assert seed_settings.seed_file(path, store) is False


def test_main_returns_zero_when_seeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    path = tmp_path / "seed.yaml"
    path.write_text(SMALL_SEED)
    monkeypatch.setattr(seed_settings, "open_store", _store)

    assert seed_settings.main(["--file", str(path)]) == 0
    assert "inserted" in capsys.readouterr().out


def test_main_reports_invalid_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    path = tmp_path / "seed.yaml"
    path.write_text("keywords: []\n")
    monkeypatch.setattr(seed_settings, "open_store", _store)

    assert seed_settings.main(["--file", str(path)]) == 2
    assert "keywords" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_seed_settings.py -q`
Expected: FAIL with `ImportError: cannot import name 'seed_settings'`

- [ ] **Step 3: Create the seed file**

Create `seeds/job_settings.yaml`. These are the current prod values from `config.yaml`, with the comments kept

```yaml
# First version of the job settings. ./seed.sh job-settings inserts this once per
# environment and never overwrites. After that, change settings at /config
keywords:
  - software engineer
  - ai engineer
  - mobile engineer
  - back end engineer

limit: 3

# jobs older than this are dropped; pair with URL param windows per site
max_age_hours: 72

filter:
  location: [jakarta, tangerang, tangerang selatan, bandung, bekasi, Indonesia]

# anchors (site, matched_keyword, title, company, url) always included
default_fields:
  - title
  - company
  - company_id
  - location
  - url
  - salary
  - salary_min
  - salary_max
  - posted_date
  - posted_at
  - work_type
  - employment_type
  - experience_level
  - job_id
  - requirements

sites:
  jobstreet:
    enabled: true
    limit: 3
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs?daterange=1&sortmode=ListedDate"
    api:
      enabled: true
      # JobStreet `where` labels; Tangerang/Bekasi also return nearby Jakarta jobs (deduped)
      locations: [Jakarta Raya, Bandung Jawa Barat, Bekasi Jawa Barat, Tangerang Banten, Tangerang Selatan Banten]
      country_wide: true

  glints:
    enabled: true
    limit: 3
    url_template: "https://glints.com/id/opportunities/jobs/explore?keyword={keyword}&country=ID&sortBy=LATEST"
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

  linkedin:
    enabled: true
    limit: 3
    # guest API ignores sortBy=DD (verified); f_TPR is the real recency lever. Kept for convention.
    url_template: "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keyword}&location=Indonesia&f_TPR=r86400&sortBy=DD&start=0"
    api:
      enabled: true
      # guest endpoint returns 429 after a few quick calls: Jakarta covers the metro area
      # (Bekasi/Tangerang results), plus one country call, with a slow pace
      locations: ["Jakarta, Indonesia"]
      country_wide: true
      delay_seconds: [4, 6]

  indeed:
    enabled: true
    limit: 3
    url_template: "https://id.indeed.com/jobs?q={keyword_plus}&l=Indonesia&fromage=1"

  upwork:
    enabled: true
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

- [ ] **Step 4: Write the seed command**

Create `scraper/seed_settings.py`

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from .config_loader import ConfigError
from .job_settings import JobSettingsStore, open_store

DEFAULT_SEED_PATH = Path("seeds/job_settings.yaml")
INVALID_SEED_EXIT_CODE = 2


def seed_file(path: Path, store: JobSettingsStore) -> bool:
    return store.seed(yaml.safe_load(path.read_text()) or {})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scraper.seed_settings",
        description="Insert the first job settings document if it is missing",
    )
    parser.add_argument("--file", type=Path, default=DEFAULT_SEED_PATH)
    args = parser.parse_args(argv)
    try:
        is_inserted = seed_file(args.file, open_store())
    except ConfigError as exc:
        print(f"[job-settings] {exc}", file=sys.stderr)
        return INVALID_SEED_EXIT_CODE
    print("[job-settings] inserted" if is_inserted else "[job-settings] already there, unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_seed_settings.py -q`
Expected: PASS

- [ ] **Step 6: Add the step to `seed.sh`**

Replace everything from the `export MONGO_URI=` line to the end of `seed.sh`

```bash
export MONGO_URI="mongodb://${MONGO_USER}:${MONGO_PASS}@${MONGO_HOST}:${MONGO_PORT}/?authSource=admin"
# `|| true`: this key is optional, and a failed grep would stop the script under set -e
MONGO_DB_NAME="${MONGO_DB_NAME:-$(_env MONGO_DB_NAME || true)}"
export MONGO_DB_NAME="${MONGO_DB_NAME:-job_scraper}"

TARGET="${1:-all}"
PYTHON="${SCRAPER_PYTHON:-${SCRIPT_DIR}/.venv/bin/python}"

seed_wilayah() {
  NODE_PATH="$(npm root -g 2>/dev/null || true)" node "${SCRIPT_DIR}/seeds/wilayah.runner.js"
}

seed_job_settings() {
  if [[ ! -x "${PYTHON}" ]]; then
    echo "ERROR: ${PYTHON} not found. Create .venv or set SCRAPER_PYTHON" >&2
    exit 1
  fi
  (cd "${SCRIPT_DIR}" && "${PYTHON}" -m scraper.seed_settings)
}

echo "[seed] target: ${MONGO_HOST}:${MONGO_PORT} (user=${MONGO_USER}, seed=${TARGET})"

case "${TARGET}" in
  all)
    seed_wilayah
    seed_job_settings
    ;;
  wilayah) seed_wilayah ;;
  job-settings) seed_job_settings ;;
  *)
    echo "Usage: $0 [all|wilayah|job-settings]" >&2
    exit 1
    ;;
esac

echo "[seed] all done"
```

- [ ] **Step 7: Check the script parses**

Run: `bash -n seed.sh`
Expected: no output

- [ ] **Step 8: Commit**

`detect-secrets` runs in pre-commit and may flag the Glints location IDs. They are public IDs, so mark those lines with `# pragma: allowlist secret` if it does

```bash
git add seeds/job_settings.yaml scraper/seed_settings.py seed.sh tests/test_seed_settings.py
git commit -m "feat: add job settings seed"
```

---

## Task 4: Move the MCP tools to the store

**Files:**
- Modify: `mcp_server/mongo.py`, `mcp_server/server.py`
- Test: `tests/test_config_tools.py`, `tests/test_scrape_jobs_ok.py`, `tests/test_mongo.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_tools.py`

```python
from __future__ import annotations

from copy import deepcopy
from typing import Any

import mongomock
import pytest

from mcp_server import server
from scraper.job_settings import JobSettingsStore

SETTINGS: dict[str, Any] = {
    "keywords": ["devops"],
    "limit": 3,
    "sites": {
        "upwork": {
            "enabled": True,
            "url_template": "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency",
        },
        "glints": {
            "enabled": False,
            "url_template": "https://glints.com/id/opportunities/jobs/explore?keyword={keyword}",
        },
    },
}


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Any:
    db = mongomock.MongoClient()["job_scraper"]
    monkeypatch.setattr(server.mongo, "get_database", lambda: db)
    JobSettingsStore(db).seed(deepcopy(SETTINGS))
    return db


def test_get_config_returns_settings_with_version(database: Any):
    result = server.get_config()

    assert result["version"] == 1
    assert result["updated_by"] == "seed"
    assert result["settings"]["keywords"] == ["devops"]


def test_get_config_reports_missing_document(monkeypatch: pytest.MonkeyPatch):
    db = mongomock.MongoClient()["job_scraper"]
    monkeypatch.setattr(server.mongo, "get_database", lambda: db)

    assert "seed.sh" in server.get_config()["error"]


def test_update_config_saves_patch(database: Any):
    result = server.update_config({"limit": 9}, expected_version=1, source="ui")

    assert result["ok"] is True
    assert result["version"] == 2
    assert result["settings"]["limit"] == 9
    assert server.get_config()["updated_by"] == "ui"


def test_update_config_reports_conflict(database: Any):
    result = server.update_config({"limit": 9}, expected_version=5)

    assert result["ok"] is False
    assert result["reason"] == "conflict"


def test_update_config_reports_invalid_patch(database: Any):
    result = server.update_config({"limit": 0})

    assert result["ok"] is False
    assert result["reason"] == "invalid"
    assert "limit" in result["message"]


def test_update_config_refuses_proxy(database: Any):
    result = server.update_config({"proxy": "socks5://localhost:1080"})

    assert result["ok"] is False
    assert result["reason"] == "invalid"


def test_update_config_reports_missing_document(monkeypatch: pytest.MonkeyPatch):
    db = mongomock.MongoClient()["job_scraper"]
    monkeypatch.setattr(server.mongo, "get_database", lambda: db)

    result = server.update_config({"limit": 9})

    assert result["ok"] is False
    assert result["reason"] == "unavailable"


def test_get_config_history_lists_versions(database: Any):
    server.update_config({"limit": 9})

    entries = server.get_config_history()["entries"]

    assert entries == [
        {
            "version": 1,
            "updated_at": entries[0]["updated_at"],
            "updated_by": "seed",
            "keywords": ["devops"],
            "enabled_sites": ["upwork"],
        }
    ]


def test_restore_config_returns_old_settings(database: Any):
    server.update_config({"limit": 9})

    result = server.restore_config(version=1, expected_version=2, source="ui")

    assert result["ok"] is True
    assert result["version"] == 3
    assert result["settings"]["limit"] == 3
```

In `tests/test_scrape_jobs_ok.py`, add this to the import block

```python
from scraper.job_settings import SettingsMissingError
```

and add this test at the end of the file

```python
@patch("mcp_server.server._load_config", side_effect=SettingsMissingError("settings missing"))
def test_ok_false_when_settings_cannot_load(mock_load):
    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result == {"ok": False, "error": "settings missing"}
```

Add to `tests/test_mongo.py`

```python
def test_get_database_uses_configured_name():
    client = MagicMock()
    with patch.object(mongo_module, "_get_client", return_value=client):
        database = mongo_module.get_database()
    assert database is client.__getitem__.return_value
    client.__getitem__.assert_called_once_with(mongo_module._DB_NAME)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config_tools.py tests/test_mongo.py tests/test_scrape_jobs_ok.py -q`
Expected: FAIL. `get_database` does not exist, and `scrape_jobs` returns no `ok` key on a config error

- [ ] **Step 3: Add `get_database`**

In `mcp_server/mongo.py`, replace `get_collection`

```python
def get_database() -> Any:
    return _get_client()[_DB_NAME]


def get_collection() -> Any:
    return get_database()[_COLLECTION_NAME]
```

- [ ] **Step 4: Change the imports in `mcp_server/server.py`**

Replace the import block at the top with

```python
from __future__ import annotations

import contextlib
import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse

from mcp.server.fastmcp import FastMCP  # type: ignore[import-untyped]
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp_server import mongo
from scraper.config import ACCEPT_LANGUAGE, USER_AGENT
from scraper.config_loader import AppConfig, ConfigError, keyword_slug
from scraper.job_settings import (
    JobSettingsStore,
    SettingsConflictError,
    SettingsMissingError,
    SettingsUnavailableError,
    StoredSettings,
    load_app_config,
)
from scraper.log import get_logger as _get_logger
```

Leave the imports that follow `scraper.log` as they are

- [ ] **Step 5: Change the helpers**

Add after `mcp = FastMCP(...)`

```python
SaveSource = Literal["ui", "mcp"]
```

Replace `_load_config`

```python
def _settings_store() -> JobSettingsStore:
    return JobSettingsStore(mongo.get_database())


def _load_config(path: Path) -> AppConfig:
    return load_app_config(path, _settings_store())
```

Delete `_deep_merge` and `_atomic_write_yaml`, then add in their place

```python
def _to_payload(stored: StoredSettings) -> dict[str, Any]:
    return {
        "version": stored.version,
        "updated_at": stored.updated_at,
        "updated_by": stored.updated_by,
        "settings": stored.settings,
    }


def _to_history_entry(entry: StoredSettings) -> dict[str, Any]:
    sites = entry.settings.get("sites", {})
    return {
        "version": entry.version,
        "updated_at": entry.updated_at,
        "updated_by": entry.updated_by,
        "keywords": entry.settings.get("keywords", []),
        "enabled_sites": [name for name, site in sites.items() if site.get("enabled", True)],
    }


def _save_result(save: Callable[[], StoredSettings]) -> dict[str, Any]:
    # The key is "message", not "error": the UI gateway treats "error" as an outage
    try:
        stored = save()
    except SettingsConflictError as exc:
        return {"ok": False, "reason": "conflict", "message": str(exc)}
    except (SettingsMissingError, SettingsUnavailableError) as exc:
        return {"ok": False, "reason": "unavailable", "message": str(exc)}
    except ConfigError as exc:
        return {"ok": False, "reason": "invalid", "message": str(exc)}
    return {"ok": True, **_to_payload(stored)}
```

- [ ] **Step 6: Replace `get_config`**

```python
@mcp.tool()
def get_config() -> dict[str, Any]:
    """Return the job settings stored in Mongo, with their version.

    Use this before update_config to see the current shape, then send a
    minimal patch to change only what you want.
    """
    try:
        return _to_payload(_settings_store().read())
    except ConfigError as exc:
        return {"error": str(exc)}
```

- [ ] **Step 7: Replace `update_config` and add the two new tools**

```python
@mcp.tool()
def update_config(
    patch: dict[str, Any],
    expected_version: int | None = None,
    source: SaveSource = "mcp",
) -> dict[str, Any]:
    """Apply a patch to the job settings after validating the result.

    Top-level keys are replaced whole. `sites` merges by site name, and each
    field of a site is replaced whole. A null value removes that key, so a site
    field goes back to the global value. The old version is kept in history.

    Args:
        patch: changes to apply. Examples:
            {"keywords": ["data analyst"]}
            {"max_age_hours": 24}
            {"sites": {"linkedin": {"enabled": false}}}
            {"sites": {"glints": {"max_age_hours": null}}}
        expected_version: version you read with get_config. When it is not the
            current version, nothing is saved and reason is "conflict".
        source: who made the change, kept with the version.

    Returns:
        On success: {ok: True, version, updated_at, updated_by, settings}
        On failure: {ok: False, reason, message}. reason is "invalid",
        "conflict", or "unavailable".
    """
    return _save_result(lambda: _settings_store().save(patch, expected_version, source))


@mcp.tool()
def get_config_history() -> dict[str, Any]:
    """Return the saved older versions of the job settings, newest first."""
    try:
        entries = _settings_store().history()
    except ConfigError as exc:
        return {"error": str(exc)}
    return {"entries": [_to_history_entry(entry) for entry in entries]}


@mcp.tool()
def restore_config(
    version: int, expected_version: int, source: SaveSource = "mcp"
) -> dict[str, Any]:
    """Make an older saved version the current job settings.

    The restore creates a new version, so it can be undone the same way.

    Args:
        version: the saved version to bring back.
        expected_version: the current version you read with get_config.
        source: who made the change, kept with the version.

    Returns:
        The same shape as update_config.
    """
    return _save_result(lambda: _settings_store().restore(version, expected_version, source))
```

- [ ] **Step 8: Fix `scrape_jobs` and the text around it**

In `scrape_jobs`, replace

```python
    except ConfigError as exc:
        log.error("scrape_jobs config error: %s", exc)
        return {"error": str(exc)}
```

with

```python
    except ConfigError as exc:
        log.error("scrape_jobs config error: %s", exc)
        return {"ok": False, "error": str(exc)}
```

Change these text strings

- `list_sites` docstring first line: `"""List sites from the job settings with their enabled status.`
- `test_proxy_connection` error: `"no proxy set in SCRAPER_PROXY_URL and proxy_url not passed — set it or pass proxy_url"`
- `test_proxy_connection` docstring at the `config.yaml` mention: use `SCRAPER_PROXY_URL` instead
- `scrape_jobs` docstring: replace `site marked enabled in config.yaml` with `site marked enabled in the job settings`, `keyword in config.yaml` with `keyword in the job settings`, and `editing config.yaml` with `changing the job settings`

- [ ] **Step 9: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_config_tools.py tests/test_mongo.py tests/test_mongo_tools.py tests/test_scrape_jobs_ok.py tests/test_proxy_mcp.py tests/test_health.py tests/test_server_sources.py -q`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add mcp_server tests/test_config_tools.py tests/test_mongo.py tests/test_scrape_jobs_ok.py
git commit -m "feat: serve job settings from Mongo in MCP tools"
```

---

## Task 5: Add save and history calls to the UI gateway

**Files:**
- Modify: `ui_server/errors.py`, `ui_server/services/mcp_gateway.py`
- Test: `tests/test_ui_mcp_gateway.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ui_mcp_gateway.py`. Change the errors import to

```python
from ui_server.errors import ConfigConflictError, ConfigInvalidError, McpUnavailableError
```

```python
def test_save_config_sends_patch_version_and_source():
    gateway = FakeGateway()
    gateway.responses = [{"ok": True, "version": 2}]

    asyncio.run(ScraperClient(gateway).save_config({"limit": 9}, 1))

    assert gateway.calls == [
        ("update_config", {"patch": {"limit": 9}, "expected_version": 1, "source": "ui"})
    ]


def test_save_config_raises_on_conflict():
    gateway = FakeGateway()
    gateway.responses = [{"ok": False, "reason": "conflict", "message": "changed"}]

    with pytest.raises(ConfigConflictError, match="changed"):
        asyncio.run(ScraperClient(gateway).save_config({"limit": 9}, 1))


def test_save_config_raises_on_invalid_settings():
    gateway = FakeGateway()
    gateway.responses = [{"ok": False, "reason": "invalid", "message": "bad limit"}]

    with pytest.raises(ConfigInvalidError, match="bad limit"):
        asyncio.run(ScraperClient(gateway).save_config({"limit": 9}, 1))


def test_save_config_raises_when_store_is_down():
    gateway = FakeGateway()
    gateway.responses = [{"ok": False, "reason": "unavailable", "message": "down"}]

    with pytest.raises(McpUnavailableError, match="down"):
        asyncio.run(ScraperClient(gateway).save_config({"limit": 9}, 1))


def test_restore_config_sends_versions_and_source():
    gateway = FakeGateway()
    gateway.responses = [{"ok": True, "version": 3}]

    asyncio.run(ScraperClient(gateway).restore_config(1, 2))

    assert gateway.calls == [
        ("restore_config", {"version": 1, "expected_version": 2, "source": "ui"})
    ]


def test_read_config_history_returns_entries():
    gateway = FakeGateway()
    gateway.responses = [{"entries": [{"version": 1}]}]

    entries = asyncio.run(ScraperClient(gateway).read_config_history())

    assert entries == [{"version": 1}]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_ui_mcp_gateway.py -q`
Expected: FAIL with `ImportError: cannot import name 'ConfigConflictError'`

- [ ] **Step 3: Add the error**

In `ui_server/errors.py`, add this class above `ConfigReadOnlyError`

```python
class ConfigConflictError(AppError):
    status_code = 409
    default_message = "These settings changed somewhere else. Reload and try again."
```

Keep `ConfigReadOnlyError` for now. `ui_server/services/config_store.py` still imports it, and Task 6 deletes both

- [ ] **Step 4: Add the client calls**

In `ui_server/services/mcp_gateway.py`, change the errors import and the constants

```python
from ui_server.errors import ConfigConflictError, ConfigInvalidError, McpUnavailableError

LOG = logging.getLogger("scraper-ui")
READ_TIMEOUT_SECONDS = 5.0
WRITE_TIMEOUT_SECONDS = 10.0
SCRAPE_TIMEOUT_SECONDS = 1800.0
CONNECT_TIMEOUT_SECONDS = 5.0
SAVE_SOURCE = "ui"
```

Add after `read_structured`

```python
def _raise_on_failed_save(result: dict[str, Any]) -> None:
    if result.get("ok"):
        return
    reason = result.get("reason")
    message = result.get("message")
    if reason == "conflict":
        raise ConfigConflictError(message)
    if reason == "invalid":
        raise ConfigInvalidError(message)
    raise McpUnavailableError(message)
```

Add to `ScraperClient`, after `read_config`

```python
    async def read_config_history(self) -> list[dict[str, Any]]:
        result = await self._gateway.call("get_config_history", {}, READ_TIMEOUT_SECONDS)
        return result["entries"]

    async def save_config(self, patch: dict[str, Any], expected_version: int) -> None:
        arguments = {"patch": patch, "expected_version": expected_version, "source": SAVE_SOURCE}
        result = await self._gateway.call("update_config", arguments, WRITE_TIMEOUT_SECONDS)
        _raise_on_failed_save(result)

    async def restore_config(self, version: int, expected_version: int) -> None:
        arguments = {
            "version": version,
            "expected_version": expected_version,
            "source": SAVE_SOURCE,
        }
        result = await self._gateway.call("restore_config", arguments, WRITE_TIMEOUT_SECONDS)
        _raise_on_failed_save(result)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_ui_mcp_gateway.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add ui_server/errors.py ui_server/services/mcp_gateway.py tests/test_ui_mcp_gateway.py
git commit -m "feat: add config save calls to the UI gateway"
```

---

## Task 6: Move the UI config API to MCP

**Files:**
- Modify: `ui_server/schema/config.py`, `ui_server/routes/config.py`, `ui_server/settings.py`, `ui_server/app.py`, `ui_server/dependencies.py`, `ui_server/errors.py`, `ui_server/requirements.txt`, `Dockerfile`
- Delete: `ui_server/services/config_store.py`, `tests/test_ui_config_store.py`
- Test: `tests/test_ui_routes.py`, `tests/test_ui_settings.py`

- [ ] **Step 1: Update the route test setup**

In `tests/test_ui_routes.py`, delete `PROXY_WITH_LOGIN` and `BASE_CONFIG`. Replace `CONFIG` with

```python
CONFIG = {
    "version": 4,
    "updated_at": "2026-11-02T01:00:00+00:00",
    "updated_by": "ui",
    "settings": {
        "keywords": ["devops"],
        "limit": 3,
        "max_age_hours": 72,
        "filter": {"location": "jakarta", "work_type": []},
        "default_fields": ["title"],
        "sites": {
            "upwork": {
                "enabled": True,
                "limit": 30,
                "filter": {},
                "url_template": "x",
                "api": {"locations": ["Remote"]},
            },
            "indeed": {"url_template": "x"},
        },
    },
}
HISTORY = [
    {
        "version": 3,
        "updated_at": "2026-11-01T01:00:00+00:00",
        "updated_by": "seed",
        "keywords": ["devops"],
        "enabled_sites": ["upwork"],
    }
]
SAVED = {"ok": True, "version": 5}
```

Replace `FakeGateway`

```python
class FakeGateway:
    def __init__(self) -> None:
        self.is_down = False
        self.config = CONFIG
        self.save_result: dict[str, Any] = SAVED
        self.scrape_delay = 0.0
        self.calls: list[str] = []
        self.arguments: dict[str, dict[str, Any]] = {}

    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        self.calls.append(tool)
        self.arguments = {**self.arguments, tool: arguments}
        if self.is_down:
            raise McpUnavailableError()
        if tool == "scrape_jobs":
            await asyncio.sleep(self.scrape_delay)
        return {
            "list_sites": SITES,
            "get_config": self.config,
            "get_config_history": {"entries": HISTORY},
            "scrape_jobs": SCRAPE_RESULT,
            "update_config": self.save_result,
            "restore_config": self.save_result,
        }[tool]
```

Replace `_settings`

```python
def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    values = {
        "env": "dev",
        "runs_dir": tmp_path / "runs",
        "log_path": tmp_path / "scraper.log",
        "static_dir": tmp_path / "dist",
    }
    return Settings(**{**values, **overrides})
```

- [ ] **Step 2: Replace the config route tests**

Delete `test_config_read_shows_locked_fields`, `test_config_read_hides_proxy_credentials`, `test_config_update_writes_file`, and `test_prod_config_is_read_only`. Add

```python
def test_config_read_returns_values_and_version(client: TestClient):
    data = client.get("/api/config").json()["data"]

    assert data["version"] == 4
    assert data["updated_by"] == "ui"
    assert data["is_stale"] is False
    assert data["values"]["filter"] == {"location": ["jakarta"]}
    assert "proxy_url" not in data["values"]


def test_config_read_keeps_site_filter_states_apart(client: TestClient):
    sites = client.get("/api/config").json()["data"]["values"]["sites"]

    assert sites[0]["filter"] == {}
    assert sites[0]["api"] == {"locations": ["Remote"]}
    assert sites[1] == {
        "name": "indeed",
        "enabled": True,
        "limit": None,
        "max_age_hours": None,
        "filter": None,
        "fields": None,
        "api": None,
    }


def test_config_read_marks_stale_values_when_mcp_is_down(
    client: TestClient, gateway: FakeGateway
):
    client.get("/api/config")
    gateway.is_down = True

    assert client.get("/api/config").json()["data"]["is_stale"] is True


def test_config_update_sends_only_changed_fields(client: TestClient, gateway: FakeGateway):
    response = client.put(
        "/api/config",
        json={
            "version": 4,
            "limit": 9,
            "sites": {
                "upwork": {
                    "max_age_hours": None,
                    "filter": {"work_type": ["remote"]},
                    "api": {
                        "enabled": True,
                        "locations": ["Remote"],
                        "country_wide": False,
                        "delay_seconds": [4, 6],
                    },
                }
            },
        },
    )

    assert response.status_code == 200
    assert gateway.arguments["update_config"] == {
        "patch": {
            "limit": 9,
            "sites": {
                "upwork": {
                    "max_age_hours": None,
                    "filter": {"work_type": ["remote"]},
                    "api": {
                        "enabled": True,
                        "locations": ["Remote"],
                        "country_wide": False,
                        "delay_seconds": [4.0, 6.0],
                    },
                }
            },
        },
        "expected_version": 4,
        "source": "ui",
    }


def test_config_update_requires_version(client: TestClient):
    assert client.put("/api/config", json={"limit": 9}).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"version": 4, "proxy_url": "socks5://localhost:1080"},
        {"version": 4, "sites": {"upwork": {"url_template": "https://evil.test"}}},
    ],
)
def test_config_update_refuses_fields_the_page_cannot_edit(client: TestClient, body: dict):
    assert client.put("/api/config", json=body).status_code == 422


def test_config_update_returns_409_on_conflict(client: TestClient, gateway: FakeGateway):
    gateway.save_result = {"ok": False, "reason": "conflict", "message": "changed"}

    response = client.put("/api/config", json={"version": 4, "limit": 9})

    assert response.status_code == 409
    assert response.json()["error"] == "changed"


def test_config_update_returns_422_on_invalid_settings(client: TestClient, gateway: FakeGateway):
    gateway.save_result = {"ok": False, "reason": "invalid", "message": "bad filter"}

    response = client.put("/api/config", json={"version": 4, "limit": 9})

    assert response.status_code == 422
    assert response.json()["error"] == "bad filter"


def test_config_history_lists_versions(client: TestClient):
    data = client.get("/api/config/history").json()["data"]

    assert data["entries"] == HISTORY


def test_config_restore_sends_versions(client: TestClient, gateway: FakeGateway):
    response = client.post("/api/config/restore", json={"version": 3, "expected_version": 4})

    assert response.status_code == 200
    assert gateway.arguments["restore_config"] == {
        "version": 3,
        "expected_version": 4,
        "source": "ui",
    }


def test_prod_config_needs_login(prod_client: TestClient):
    assert prod_client.get("/api/config").status_code == 401
    assert prod_client.put("/api/config", json={"version": 4, "limit": 9}).status_code == 401
    assert (
        prod_client.post(
            "/api/config/restore", json={"version": 3, "expected_version": 4}
        ).status_code
        == 401
    )


def test_prod_config_can_be_saved_after_login(prod_client: TestClient, gateway: FakeGateway):
    prod_client.post("/api/auth/login", json={"password": PASSWORD})

    response = prod_client.put("/api/config", json={"version": 4, "limit": 9})

    assert response.status_code == 200
    assert "update_config" in gateway.calls
```

Check `test_cross_site_write_is_refused`: its body has no `version`, which is fine because the cross-site check runs first. Keep it

- [ ] **Step 3: Update the settings tests**

In `tests/test_ui_settings.py`, delete both `config_read_only` assert lines and rename `test_prod_turns_on_login_and_read_only_config` to `test_prod_turns_on_login`

- [ ] **Step 4: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_ui_routes.py tests/test_ui_settings.py -q`
Expected: FAIL on the new config route tests

- [ ] **Step 5: Replace the schema**

Replace `ui_server/schema/config.py`

```python
from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_LIMIT = 200
MAX_AGE_HOURS = 720
MAX_LIST_ITEMS = 100

Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
SiteName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]+$", max_length=40)]
FieldName = Annotated[str, StringConstraints(pattern=r"^[a-z_]+$", max_length=40)]
TextItem = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
TextList = Annotated[list[TextItem], Field(max_length=MAX_LIST_ITEMS)]
FieldList = Annotated[list[FieldName], Field(max_length=MAX_LIST_ITEMS)]


class FilterSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: TextList = Field(default_factory=list)
    employment_type: TextList = Field(default_factory=list)
    work_type: TextList = Field(default_factory=list)


class ApiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    locations: TextList
    country_wide: bool
    delay_seconds: tuple[float, float] | None = None


class SiteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    limit: int | None = Field(default=None, ge=1, le=MAX_LIMIT)
    max_age_hours: int | None = Field(default=None, ge=1, le=MAX_AGE_HOURS)
    filter: FilterSettings | None = None
    fields: FieldList | None = None
    api: ApiSettings | None = None


class ConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    keywords: list[Keyword] | None = Field(default=None, min_length=1)
    limit: int | None = Field(default=None, ge=1, le=MAX_LIMIT)
    max_age_hours: int | None = Field(default=None, ge=1, le=MAX_AGE_HOURS)
    filter: FilterSettings | None = None
    default_fields: FieldList | None = None
    sites: dict[SiteName, SiteUpdate] = Field(default_factory=dict)

    def to_patch(self) -> dict[str, Any]:
        # exclude_unset keeps explicit nulls, which remove a key from the settings
        return self.model_dump(mode="json", exclude_unset=True, exclude={"version"})


class ConfigRestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    expected_version: int = Field(ge=1)
```

- [ ] **Step 6: Replace the routes**

Replace `ui_server/routes/config.py`

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ui_server.dependencies import ServicesDep, require_session
from ui_server.schema.config import ConfigRestoreRequest, ConfigUpdateRequest
from ui_server.schema.response import ok

router = APIRouter(prefix="/api/config", dependencies=[Depends(require_session)])


def _to_filter(raw: dict[str, Any] | None) -> dict[str, list[str]] | None:
    if raw is None:
        return None
    return {
        key: [value] if isinstance(value, str) else value for key, value in raw.items() if value
    }


def _to_site(name: str, site: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "enabled": site.get("enabled", True),
        "limit": site.get("limit"),
        "max_age_hours": site.get("max_age_hours"),
        "filter": _to_filter(site.get("filter")),
        "fields": site.get("fields"),
        "api": site.get("api"),
    }


def _to_values(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "keywords": settings.get("keywords", []),
        "limit": settings.get("limit"),
        "max_age_hours": settings.get("max_age_hours"),
        "filter": _to_filter(settings.get("filter")) or {},
        "default_fields": settings.get("default_fields", []),
        "sites": [_to_site(name, site) for name, site in settings.get("sites", {}).items()],
    }


@router.get("")
async def read_config(services: ServicesDep) -> dict[str, Any]:
    read = await services.scraper.read_config()
    return ok(
        {
            "values": _to_values(read.value["settings"]),
            "version": read.value["version"],
            "updated_at": read.value["updated_at"],
            "updated_by": read.value["updated_by"],
            "is_stale": read.is_stale,
        }
    )


@router.put("")
async def update_config(body: ConfigUpdateRequest, services: ServicesDep) -> dict[str, Any]:
    await services.scraper.save_config(body.to_patch(), body.version)
    return ok(None)


@router.get("/history")
async def read_history(services: ServicesDep) -> dict[str, Any]:
    return ok({"entries": await services.scraper.read_config_history()})


@router.post("/restore")
async def restore_config(body: ConfigRestoreRequest, services: ServicesDep) -> dict[str, Any]:
    await services.scraper.restore_config(body.version, body.expected_version)
    return ok(None)
```

- [ ] **Step 7: Remove the file store**

```bash
git rm ui_server/services/config_store.py tests/test_ui_config_store.py
```

In `ui_server/app.py`, delete the `ConfigStore` import and the `config_store=ConfigStore(settings),` line

In `ui_server/dependencies.py`, delete the `ConfigStore` import and the `config_store: ConfigStore` field

In `ui_server/settings.py`, delete `config_path`, `dev_patch_path`, `dev_merged_path`, `backup_dir`, and the `config_read_only` property

In `ui_server/errors.py`, delete `ConfigReadOnlyError`

In `ui_server/requirements.txt`, delete `pyyaml>=6.0` and `ruamel.yaml>=0.18,<1`

In `Dockerfile`, in the `ui-server` stage, delete this line

```dockerfile
COPY --chown=uiuser:uiuser scraper/__init__.py scraper/config_loader.py scraper/types.py ./scraper/
```

and change the `mkdir` line to

```dockerfile
 && mkdir -p /app/output /app/logs \
```

- [ ] **Step 8: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_ui_routes.py tests/test_ui_settings.py tests/test_ui_errors.py tests/test_ui_mcp_gateway.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add -A ui_server tests/test_ui_routes.py tests/test_ui_settings.py Dockerfile
git commit -m "feat: save scraper config through MCP in every environment"
```

---

## Task 7: Move the CLI to Mongo and remove `load`

**Files:**
- Modify: `scraper/__main__.py`, `scraper/__init__.py`, `scraper/config_loader.py`
- Test: `tests/test_cli.py`, `tests/test_config_api.py`, `tests/test_runner_api_wiring.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`

```python
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import mongomock
import pytest

from scraper import __main__ as cli
from scraper.config_loader import PROXY_ENV_VAR
from scraper.job_settings import JobSettingsStore

SETTINGS: dict[str, Any] = {
    "keywords": ["devops"],
    "sites": {
        "upwork": {
            "url_template": "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency",
        }
    },
}


def _config_file(tmp_path: Path) -> str:
    path = tmp_path / "config.yaml"
    path.write_text("concurrency: 1\n")
    return str(path)


def test_cli_runs_with_settings_from_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])
    store.seed(deepcopy(SETTINGS))
    calls: list[tuple[Any, Any, Any]] = []
    monkeypatch.setenv(PROXY_ENV_VAR, "")
    monkeypatch.setattr(cli, "open_store", lambda: store)
    monkeypatch.setattr(
        cli, "run", lambda config, targets, keywords: calls.append((config, targets, keywords)) or 0
    )

    code = cli.main(["--config", _config_file(tmp_path), "-k", "python", "upwork"])

    assert code == 0
    assert calls[0][0].keywords == ("devops",)
    assert calls[0][1] == ["upwork"]
    assert calls[0][2] == ["python"]


def test_cli_reports_missing_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])
    monkeypatch.setenv(PROXY_ENV_VAR, "")
    monkeypatch.setattr(cli, "open_store", lambda: store)

    assert cli.main(["--config", _config_file(tmp_path)]) == 2
    assert "seed.sh" in capsys.readouterr().err
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py -q`
Expected: FAIL with `AttributeError` on `open_store`

- [ ] **Step 3: Change the CLI**

In `scraper/__main__.py`, change the imports and text

```python
from .config_loader import ConfigError
from .job_settings import load_app_config, open_store
from .runner import run
```

```python
    parser = argparse.ArgumentParser(
        prog="scraper",
        description="Scrape job listings using the job settings stored in Mongo",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="path to the machine settings YAML (default: ./config.yaml)",
    )
```

Keep the `--keyword` help as `override keyword(s) from the job settings; pass --keyword multiple times for several`, and the `sites` help as `optional site names to run; overrides 'enabled' flags in the job settings`

In `main`, replace `config = load(args.config)` with

```python
        config = load_app_config(args.config, open_store())
```

- [ ] **Step 4: Remove `load`**

Delete the `load` function from `scraper/config_loader.py`

Replace `scraper/__init__.py`

```python
from __future__ import annotations

from .config_loader import AppConfig, ConfigError, SiteConfig, parse
from .types import Job

__all__ = ["AppConfig", "ConfigError", "Job", "SiteConfig", "parse"]
```

- [ ] **Step 5: Update the old tests**

Replace `tests/test_config_api.py`

```python
from __future__ import annotations

import pytest
import yaml

from scraper.api.registry import API_SOURCES
from scraper.config_loader import ApiConfig, AppConfig, ConfigError, parse

BASE = """
keywords: [devops]
sites:
  jobstreet:
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs"
"""


def _parse(extra: str) -> AppConfig:
    return parse(yaml.safe_load(BASE + extra), None)


def test_api_block_parsed():
    site = _parse(
        """    api:
      enabled: true
      locations: [Jakarta Raya, Bandung Jawa Barat]
      country_wide: true
""",
    ).site("jobstreet")
    assert site is not None
    assert site.api == ApiConfig(
        enabled=True, locations=("Jakarta Raya", "Bandung Jawa Barat"), country_wide=True
    )


def test_missing_api_block_is_none():
    site = _parse("").site("jobstreet")
    assert site is not None
    assert site.api is None


def test_api_defaults():
    site = _parse("    api: {}\n").site("jobstreet")
    assert site is not None
    assert site.api == ApiConfig(enabled=True, locations=(), country_wide=False)


def test_locations_must_be_list_of_strings():
    with pytest.raises(ConfigError, match="sites.jobstreet.api.locations"):
        _parse("    api:\n      locations: Jakarta\n")


def test_registry_has_api_sites():
    assert set(API_SOURCES) == {"jobstreet", "glints", "linkedin", "upwork"}


def test_delay_seconds_parsed():
    site = _parse("    api:\n      delay_seconds: [4, 6]\n").site("jobstreet")
    assert site is not None
    assert site.api is not None
    assert site.api.delay_seconds == (4.0, 6.0)


def test_delay_seconds_defaults_to_none():
    site = _parse("    api: {}\n").site("jobstreet")
    assert site is not None
    assert site.api is not None
    assert site.api.delay_seconds is None


@pytest.mark.parametrize("bad", ["5", "[6, 4]", "[-1, 2]", "[1, 2, 3]", "[a, b]"])
def test_delay_seconds_must_be_valid_range(bad: str):
    with pytest.raises(ConfigError, match="sites.jobstreet.api.delay_seconds"):
        _parse(f"    api:\n      delay_seconds: {bad}\n")


def test_upwork_site_bypasses_the_global_location_filter():
    config = parse(
        yaml.safe_load(
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
        ),
        None,
    )

    assert config.filter_for("upwork") == {}
    assert config.limit_for("upwork") == 30
    site = config.site("upwork")
    assert site is not None
    assert site.api is not None
    assert site.api.locations == ("Remote",)
```

In `tests/test_runner_api_wiring.py`, change the import to `from scraper.config_loader import ApiConfig, parse`, add `import yaml` to the imports, and change the end of `test_run_wires_api_callbacks_into_run_one`. Replace the `config_path` lines

```python
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
```

with

```python
    raw_config = yaml.safe_load(
        f"""
```

and replace `assert runner.run(load(config_path)) == 0` with

```python
    assert runner.run(parse(raw_config, None)) == 0
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 7: Check nothing still calls `load`**

Run: `grep -rnE "config_loader import .*\bload\b|\bload\(args|\bload\(path" scraper mcp_server ui_server tests`
Expected: no output

- [ ] **Step 8: Commit**

```bash
git add scraper tests/test_cli.py tests/test_config_api.py tests/test_runner_api_wiring.py
git commit -m "feat: read job settings from Mongo in the CLI"
```

---

## Task 8: Update the frontend domain and model

**Files:**
- Modify: `ui/src/modules/config/domain/entities/ScraperConfig.ts`, `ui/src/modules/config/data/models/ConfigModel.ts`
- Test: `ui/src/modules/config/domain/entities/__tests__/ScraperConfig.spec.ts`, `ui/src/modules/config/data/models/__tests__/ConfigModel.spec.ts`

- [ ] **Step 1: Write the failing domain tests**

Replace `ui/src/modules/config/domain/entities/__tests__/ScraperConfig.spec.ts`

```ts
import { describe, expect, it } from 'vitest'
import {
  EMPTY_FILTER,
  hasConfigChanges,
  toConfigChanges,
  toDelaySeconds,
  toOptionalNumber,
  type ConfigValues,
  type SiteSetting,
} from '@/modules/config/domain/entities/ScraperConfig'

const SITE: SiteSetting = {
  name: 'upwork',
  isEnabled: true,
  limit: 30,
  maxAgeHours: null,
  filter: EMPTY_FILTER,
  fields: null,
  api: { isEnabled: true, locations: ['Remote'], isCountryWide: false, delaySeconds: null },
}

const ORIGINAL: ConfigValues = {
  keywords: ['django'],
  limit: 3,
  maxAgeHours: 72,
  filter: { ...EMPTY_FILTER, location: ['jakarta'] },
  defaultFields: ['title'],
  sites: [SITE],
}

function withSite(changes: Partial<SiteSetting>): ConfigValues {
  return { ...ORIGINAL, sites: [{ ...SITE, ...changes }] }
}

describe('toConfigChanges', () => {
  it('sends nothing when nothing changed', () => {
    expect(hasConfigChanges(toConfigChanges(ORIGINAL, ORIGINAL))).toBe(false)
  })

  it('sends only the changed field', () => {
    expect(toConfigChanges({ ...ORIGINAL, limit: 9 }, ORIGINAL)).toEqual({ limit: 9 })
  })

  it('sends a changed filter whole', () => {
    const filter = { ...EMPTY_FILTER, workType: ['remote'] }

    expect(toConfigChanges({ ...ORIGINAL, filter }, ORIGINAL)).toEqual({ filter })
  })

  it('sends changed default fields', () => {
    const changes = toConfigChanges({ ...ORIGINAL, defaultFields: ['title', 'url'] }, ORIGINAL)

    expect(changes).toEqual({ defaultFields: ['title', 'url'] })
  })

  it('sends only the changed site field', () => {
    expect(toConfigChanges(withSite({ isEnabled: false }), ORIGINAL)).toEqual({
      sites: { upwork: { isEnabled: false } },
    })
  })

  it('sends null when a site goes back to the global value', () => {
    expect(toConfigChanges(withSite({ limit: null, filter: null }), ORIGINAL)).toEqual({
      sites: { upwork: { limit: null, filter: null } },
    })
  })

  it('sends a changed api block whole', () => {
    const api = { ...SITE.api!, delaySeconds: [4, 6] as [number, number] }

    expect(toConfigChanges(withSite({ api }), ORIGINAL)).toEqual({
      sites: { upwork: { api } },
    })
  })

  it('leaves out emptied global numbers', () => {
    expect(toConfigChanges({ ...ORIGINAL, limit: null, maxAgeHours: null }, ORIGINAL)).toEqual({})
  })
})

describe('toOptionalNumber', () => {
  it('turns input text into a number', () => {
    expect(toOptionalNumber('12')).toBe(12)
  })

  it('turns empty input into null', () => {
    expect(toOptionalNumber('')).toBeNull()
  })
})

describe('toDelaySeconds', () => {
  it('keeps both values', () => {
    expect(toDelaySeconds(4, 6)).toEqual([4, 6])
  })

  it('turns two empty values into null', () => {
    expect(toDelaySeconds(null, null)).toBeNull()
  })

  it('fills a missing value from the other one', () => {
    expect(toDelaySeconds(4, null)).toEqual([4, 4])
    expect(toDelaySeconds(null, 6)).toEqual([6, 6])
  })
})
```

- [ ] **Step 2: Write the failing model tests**

Replace `ui/src/modules/config/data/models/__tests__/ConfigModel.spec.ts`

```ts
import { describe, expect, it } from 'vitest'
import {
  toConfigChangesModel,
  toConfigSnapshot,
  toConfigVersions,
  type ConfigModel,
} from '@/modules/config/data/models/ConfigModel'

const MODEL: ConfigModel = {
  values: {
    keywords: ['django'],
    limit: 3,
    max_age_hours: 72,
    filter: { location: ['jakarta'] },
    default_fields: ['title'],
    sites: [
      {
        name: 'upwork',
        enabled: true,
        limit: 30,
        max_age_hours: null,
        filter: {},
        fields: null,
        api: { locations: ['Remote'] },
      },
      {
        name: 'indeed',
        enabled: false,
        limit: null,
        max_age_hours: 24,
        filter: null,
        fields: ['title'],
        api: null,
      },
    ],
  },
  version: 4,
  updated_at: '2026-11-02T01:00:00+00:00',
  updated_by: 'ui',
  is_stale: false,
}

describe('toConfigSnapshot', () => {
  it('maps API names and fills filter lists', () => {
    const snapshot = toConfigSnapshot(MODEL)

    expect(snapshot.version).toBe(4)
    expect(snapshot.updatedBy).toBe('ui')
    expect(snapshot.values.filter).toEqual({ location: ['jakarta'], employmentType: [], workType: [] })
    expect(snapshot.values.defaultFields).toEqual(['title'])
  })

  it('keeps no filter apart from the global filter', () => {
    const [upwork, indeed] = toConfigSnapshot(MODEL).values.sites

    expect(upwork?.filter).toEqual({ location: [], employmentType: [], workType: [] })
    expect(indeed?.filter).toBeNull()
  })

  it('fills api defaults', () => {
    const [upwork, indeed] = toConfigSnapshot(MODEL).values.sites

    expect(upwork?.api).toEqual({
      isEnabled: true,
      locations: ['Remote'],
      isCountryWide: false,
      delaySeconds: null,
    })
    expect(indeed?.api).toBeNull()
  })
})

describe('toConfigChangesModel', () => {
  it('maps changed fields to API names', () => {
    const model = toConfigChangesModel({
      maxAgeHours: 24,
      defaultFields: ['title'],
      sites: {
        upwork: {
          isEnabled: false,
          maxAgeHours: null,
          filter: { location: [], employmentType: ['contract'], workType: [] },
          api: { isEnabled: true, locations: ['Remote'], isCountryWide: true, delaySeconds: [4, 6] },
        },
      },
    })

    expect(model).toEqual({
      max_age_hours: 24,
      default_fields: ['title'],
      sites: {
        upwork: {
          enabled: false,
          max_age_hours: null,
          filter: { employment_type: ['contract'] },
          api: { enabled: true, locations: ['Remote'], country_wide: true, delay_seconds: [4, 6] },
        },
      },
    })
  })

  it('keeps null for a site that goes back to the global filter', () => {
    expect(toConfigChangesModel({ sites: { upwork: { filter: null } } })).toEqual({
      sites: { upwork: { filter: null } },
    })
  })

  it('sends an empty filter for no filter', () => {
    const filter = { location: [], employmentType: [], workType: [] }

    expect(toConfigChangesModel({ sites: { upwork: { filter } } })).toEqual({
      sites: { upwork: { filter: {} } },
    })
  })

  it('leaves out fields that did not change', () => {
    expect(toConfigChangesModel({ limit: 9 })).toEqual({ limit: 9 })
  })
})

describe('toConfigVersions', () => {
  it('maps history entries', () => {
    const versions = toConfigVersions({
      entries: [
        {
          version: 3,
          updated_at: '2026-11-01T01:00:00+00:00',
          updated_by: 'seed',
          keywords: ['django'],
          enabled_sites: ['upwork'],
        },
      ],
    })

    expect(versions).toEqual([
      {
        version: 3,
        updatedAt: '2026-11-01T01:00:00+00:00',
        updatedBy: 'seed',
        keywords: ['django'],
        enabledSites: ['upwork'],
      },
    ])
  })
})
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd ui && bunx vitest run src/modules/config/domain src/modules/config/data`
Expected: FAIL. `EMPTY_FILTER` and `toConfigVersions` do not exist

- [ ] **Step 4: Replace the domain file**

Replace `ui/src/modules/config/domain/entities/ScraperConfig.ts`

```ts
export interface FilterSetting {
  location: string[]
  employmentType: string[]
  workType: string[]
}

export interface ApiSetting {
  isEnabled: boolean
  locations: string[]
  isCountryWide: boolean
  delaySeconds: [number, number] | null
}

export interface SiteSetting {
  name: string
  isEnabled: boolean
  limit: number | null
  maxAgeHours: number | null
  filter: FilterSetting | null
  fields: string[] | null
  api: ApiSetting | null
}

export interface ConfigValues {
  keywords: string[]
  limit: number | null
  maxAgeHours: number | null
  filter: FilterSetting
  defaultFields: string[]
  sites: SiteSetting[]
}

export interface ConfigSnapshot {
  values: ConfigValues
  version: number
  updatedAt: string
  updatedBy: string
  isStale: boolean
}

export interface ConfigVersion {
  version: number
  updatedAt: string
  updatedBy: string
  keywords: string[]
  enabledSites: string[]
}

export type SiteChanges = Partial<Omit<SiteSetting, 'name'>>

export interface ConfigChanges {
  keywords?: string[]
  limit?: number
  maxAgeHours?: number
  filter?: FilterSetting
  defaultFields?: string[]
  sites?: Record<string, SiteChanges>
}

export const EMPTY_FILTER: FilterSetting = { location: [], employmentType: [], workType: [] }

const SITE_FIELDS = ['isEnabled', 'limit', 'maxAgeHours', 'filter', 'fields', 'api'] as const

export function toOptionalNumber(value: string | number): number | null {
  return value === '' ? null : Number(value)
}

export function toDelaySeconds(min: number | null, max: number | null): [number, number] | null {
  if (min === null && max === null) {
    return null
  }
  return [min ?? (max as number), max ?? (min as number)]
}

function isSame(first: unknown, second: unknown): boolean {
  return JSON.stringify(first) === JSON.stringify(second)
}

function toSiteChanges(site: SiteSetting, original: SiteSetting | undefined): SiteChanges {
  const changed = SITE_FIELDS.filter((field) => !isSame(site[field], original?.[field]))
  return Object.fromEntries(changed.map((field) => [field, site[field]])) as SiteChanges
}

function toSitesChanges(
  values: ConfigValues,
  original: ConfigValues,
): Record<string, SiteChanges> {
  const entries = values.sites.map((site): [string, SiteChanges] => [
    site.name,
    toSiteChanges(
      site,
      original.sites.find((candidate) => candidate.name === site.name),
    ),
  ])
  return Object.fromEntries(entries.filter(([, changes]) => Object.keys(changes).length > 0))
}

export function toConfigChanges(values: ConfigValues, original: ConfigValues): ConfigChanges {
  const sites = toSitesChanges(values, original)
  const isLimitKept = values.limit === null || values.limit === original.limit
  const isMaxAgeKept = values.maxAgeHours === null || values.maxAgeHours === original.maxAgeHours
  return {
    ...(isSame(values.keywords, original.keywords) ? {} : { keywords: values.keywords }),
    ...(isLimitKept ? {} : { limit: values.limit as number }),
    ...(isMaxAgeKept ? {} : { maxAgeHours: values.maxAgeHours as number }),
    ...(isSame(values.filter, original.filter) ? {} : { filter: values.filter }),
    ...(isSame(values.defaultFields, original.defaultFields)
      ? {}
      : { defaultFields: values.defaultFields }),
    ...(Object.keys(sites).length > 0 ? { sites } : {}),
  }
}

export function hasConfigChanges(changes: ConfigChanges): boolean {
  return Object.keys(changes).length > 0
}
```

- [ ] **Step 5: Replace the model file**

Replace `ui/src/modules/config/data/models/ConfigModel.ts`

```ts
import type {
  ApiSetting,
  ConfigChanges,
  ConfigSnapshot,
  ConfigVersion,
  FilterSetting,
  SiteChanges,
  SiteSetting,
} from '@/modules/config/domain/entities/ScraperConfig'

export interface FilterModel {
  location?: string[]
  employment_type?: string[]
  work_type?: string[]
}

export interface ApiModel {
  enabled?: boolean
  locations?: string[]
  country_wide?: boolean
  delay_seconds?: [number, number] | null
}

export interface SiteModel {
  name: string
  enabled: boolean
  limit: number | null
  max_age_hours: number | null
  filter: FilterModel | null
  fields: string[] | null
  api: ApiModel | null
}

export interface ConfigModel {
  values: {
    keywords: string[]
    limit: number | null
    max_age_hours: number | null
    filter: FilterModel
    default_fields: string[]
    sites: SiteModel[]
  }
  version: number
  updated_at: string
  updated_by: string
  is_stale: boolean
}

export interface SiteChangesModel {
  enabled?: boolean
  limit?: number | null
  max_age_hours?: number | null
  filter?: FilterModel | null
  fields?: string[] | null
  api?: ApiModel | null
}

export interface ConfigChangesModel {
  keywords?: string[]
  limit?: number
  max_age_hours?: number
  filter?: FilterModel
  default_fields?: string[]
  sites?: Record<string, SiteChangesModel>
}

export interface ConfigHistoryModel {
  entries: {
    version: number
    updated_at: string
    updated_by: string
    keywords: string[]
    enabled_sites: string[]
  }[]
}

function toFilterSetting(model: FilterModel): FilterSetting {
  return {
    location: model.location ?? [],
    employmentType: model.employment_type ?? [],
    workType: model.work_type ?? [],
  }
}

function toApiSetting(model: ApiModel): ApiSetting {
  return {
    isEnabled: model.enabled ?? true,
    locations: model.locations ?? [],
    isCountryWide: model.country_wide ?? false,
    delaySeconds: model.delay_seconds ?? null,
  }
}

function toSiteSetting(model: SiteModel): SiteSetting {
  return {
    name: model.name,
    isEnabled: model.enabled,
    limit: model.limit,
    maxAgeHours: model.max_age_hours,
    filter: model.filter === null ? null : toFilterSetting(model.filter),
    fields: model.fields,
    api: model.api === null ? null : toApiSetting(model.api),
  }
}

export function toConfigSnapshot(model: ConfigModel): ConfigSnapshot {
  return {
    values: {
      keywords: model.values.keywords,
      limit: model.values.limit,
      maxAgeHours: model.values.max_age_hours,
      filter: toFilterSetting(model.values.filter),
      defaultFields: model.values.default_fields,
      sites: model.values.sites.map(toSiteSetting),
    },
    version: model.version,
    updatedAt: model.updated_at,
    updatedBy: model.updated_by,
    isStale: model.is_stale,
  }
}

export function toConfigVersions(model: ConfigHistoryModel): ConfigVersion[] {
  return model.entries.map((entry) => ({
    version: entry.version,
    updatedAt: entry.updated_at,
    updatedBy: entry.updated_by,
    keywords: entry.keywords,
    enabledSites: entry.enabled_sites,
  }))
}

function toFilterModel(filter: FilterSetting): FilterModel {
  return {
    ...(filter.location.length > 0 ? { location: filter.location } : {}),
    ...(filter.employmentType.length > 0 ? { employment_type: filter.employmentType } : {}),
    ...(filter.workType.length > 0 ? { work_type: filter.workType } : {}),
  }
}

function toApiModel(api: ApiSetting): ApiModel {
  return {
    enabled: api.isEnabled,
    locations: api.locations,
    country_wide: api.isCountryWide,
    delay_seconds: api.delaySeconds,
  }
}

function toSiteChangesModel(changes: SiteChanges): SiteChangesModel {
  const { isEnabled, maxAgeHours, filter, api, ...shared } = changes
  return {
    ...shared,
    ...(isEnabled === undefined ? {} : { enabled: isEnabled }),
    ...(maxAgeHours === undefined ? {} : { max_age_hours: maxAgeHours }),
    ...(filter === undefined ? {} : { filter: filter === null ? null : toFilterModel(filter) }),
    ...(api === undefined ? {} : { api: api === null ? null : toApiModel(api) }),
  }
}

export function toConfigChangesModel(changes: ConfigChanges): ConfigChangesModel {
  const { maxAgeHours, filter, defaultFields, sites, ...shared } = changes
  return {
    ...shared,
    ...(maxAgeHours === undefined ? {} : { max_age_hours: maxAgeHours }),
    ...(filter === undefined ? {} : { filter: toFilterModel(filter) }),
    ...(defaultFields === undefined ? {} : { default_fields: defaultFields }),
    ...(sites === undefined
      ? {}
      : {
          sites: Object.fromEntries(
            Object.entries(sites).map(([name, site]) => [name, toSiteChangesModel(site)]),
          ),
        }),
  }
}
```

- [ ] **Step 6: Run the tests**

Run: `cd ui && bunx vitest run src/modules/config/domain src/modules/config/data`
Expected: PASS

- [ ] **Step 7: Commit**

`ConfigRepositoryImpl`, the store, and the page do not compile against these types yet. Tasks 9 and 11 fix that, so do not run `type-check` until Task 11

```bash
git add ui/src/modules/config/domain/entities ui/src/modules/config/data/models
git commit -m "feat: extend config model for all job settings"
```

---

## Task 9: Update the data layer, use cases, and store

**Files:**
- Create: `ui/src/modules/config/domain/usecases/GetConfigHistoryUseCase.ts`, `ui/src/modules/config/domain/usecases/RestoreConfigUseCase.ts`
- Modify: `ConfigRemoteDataSource.ts`, `ConfigRepositoryImpl.ts`, `ConfigRepository.ts`, `SaveConfigUseCase.ts`, `configUseCases.ts`, `useConfigStore.ts`, `routes.ts`
- Test: `ui/src/modules/config/presentation/stores/__tests__/useConfigStore.spec.ts`

- [ ] **Step 1: Write the failing store tests**

Replace `ui/src/modules/config/presentation/stores/__tests__/useConfigStore.spec.ts`

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import {
  EMPTY_FILTER,
  type ConfigSnapshot,
} from '@/modules/config/domain/entities/ScraperConfig'
import { provideConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'

const getConfig = { execute: vi.fn() }
const saveConfig = { execute: vi.fn() }
const getConfigHistory = { execute: vi.fn() }
const restoreConfig = { execute: vi.fn() }

const SNAPSHOT: ConfigSnapshot = {
  values: {
    keywords: ['django'],
    limit: 3,
    maxAgeHours: 72,
    filter: EMPTY_FILTER,
    defaultFields: ['title'],
    sites: [],
  },
  version: 4,
  updatedAt: '2026-11-02T01:00:00+00:00',
  updatedBy: 'ui',
  isStale: false,
}

const VERSION = {
  version: 3,
  updatedAt: '2026-11-01T01:00:00+00:00',
  updatedBy: 'seed',
  keywords: ['django'],
  enabledSites: ['upwork'],
}

describe('useConfigStore', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    getConfigHistory.execute.mockResolvedValue([])
    provideConfigUseCases({ getConfig, saveConfig, getConfigHistory, restoreConfig })
  })

  it('loads a copy of the values', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const store = useConfigStore()

    await store.load()

    expect(store.status).toBe('ready')
    expect(store.values).toEqual(SNAPSHOT.values)
    expect(store.values).not.toBe(SNAPSHOT.values)
    expect(store.values?.filter).not.toBe(SNAPSHOT.values.filter)
  })

  it('shows an error when load fails', async () => {
    getConfig.execute.mockRejectedValue(new Error('Scraper down'))
    const store = useConfigStore()

    await store.load()

    expect(store.status).toBe('error')
    expect(store.errorMessage).toBe('Scraper down')
  })

  it('saves changed values with the loaded version then reloads', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    saveConfig.execute.mockResolvedValue(undefined)
    const store = useConfigStore()
    await store.load()
    store.values!.limit = 9

    await expect(store.save()).resolves.toBe(true)

    expect(saveConfig.execute).toHaveBeenCalledWith({ limit: 9 }, 4)
    expect(getConfig.execute).toHaveBeenCalledTimes(2)
    expect(getConfigHistory.execute).toHaveBeenCalledTimes(1)
  })

  it('skips the save when nothing changed', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const store = useConfigStore()
    await store.load()

    await expect(store.save()).resolves.toBe(true)

    expect(saveConfig.execute).not.toHaveBeenCalled()
  })

  it('keeps the message when save fails', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    saveConfig.execute.mockRejectedValue(new Error('Bad config'))
    const store = useConfigStore()
    await store.load()
    store.values!.limit = 9

    await expect(store.save()).resolves.toBe(false)

    expect(store.saveError).toBe('Bad config')
  })

  it('does not save stale values', async () => {
    getConfig.execute.mockResolvedValue({ ...SNAPSHOT, isStale: true })
    const store = useConfigStore()
    await store.load()
    store.values!.limit = 9

    await expect(store.save()).resolves.toBe(false)

    expect(saveConfig.execute).not.toHaveBeenCalled()
  })

  it('loads history', async () => {
    getConfigHistory.execute.mockResolvedValue([VERSION])
    const store = useConfigStore()

    await store.loadHistory()

    expect(store.history).toEqual([VERSION])
  })

  it('shows an error when history fails', async () => {
    getConfigHistory.execute.mockRejectedValue(new Error('History down'))
    const store = useConfigStore()

    await store.loadHistory()

    expect(store.historyError).toBe('History down')
  })

  it('restores with the loaded version then reloads', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    restoreConfig.execute.mockResolvedValue(undefined)
    const store = useConfigStore()
    await store.load()

    await expect(store.restore(3)).resolves.toBe(true)

    expect(restoreConfig.execute).toHaveBeenCalledWith(3, 4)
    expect(getConfig.execute).toHaveBeenCalledTimes(2)
    expect(getConfigHistory.execute).toHaveBeenCalledTimes(1)
  })

  it('keeps the message when restore fails', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    restoreConfig.execute.mockRejectedValue(new Error('Conflict'))
    const store = useConfigStore()
    await store.load()

    await expect(store.restore(3)).resolves.toBe(false)

    expect(store.saveError).toBe('Conflict')
  })

  it('does not restore over stale values', async () => {
    getConfig.execute.mockResolvedValue({ ...SNAPSHOT, isStale: true })
    const store = useConfigStore()
    await store.load()

    await expect(store.restore(3)).resolves.toBe(false)

    expect(restoreConfig.execute).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ui && bunx vitest run src/modules/config/presentation/stores`
Expected: FAIL on the save, history, and restore tests

- [ ] **Step 3: Update the repository contract**

Replace `ui/src/modules/config/domain/repositories/ConfigRepository.ts`

```ts
import type {
  ConfigChanges,
  ConfigSnapshot,
  ConfigVersion,
} from '@/modules/config/domain/entities/ScraperConfig'

export interface ConfigRepository {
  getConfig(): Promise<ConfigSnapshot>
  saveConfig(changes: ConfigChanges, version: number): Promise<void>
  getConfigHistory(): Promise<ConfigVersion[]>
  restoreConfig(version: number, expectedVersion: number): Promise<void>
}
```

- [ ] **Step 4: Update the data source**

Replace `ui/src/modules/config/data/datasources/ConfigRemoteDataSource.ts`

```ts
import type { HttpClient } from '@/core/http/httpClient'
import type {
  ConfigChangesModel,
  ConfigHistoryModel,
  ConfigModel,
} from '@/modules/config/data/models/ConfigModel'

const CONFIG_PATH = '/config'
const HISTORY_PATH = '/config/history'
const RESTORE_PATH = '/config/restore'

export class ConfigRemoteDataSource {
  private readonly client: HttpClient

  constructor(client: HttpClient) {
    this.client = client
  }

  getConfig(): Promise<ConfigModel> {
    return this.client.get<ConfigModel>(CONFIG_PATH)
  }

  saveConfig(changes: ConfigChangesModel, version: number): Promise<void> {
    return this.client.put<void>(CONFIG_PATH, { ...changes, version })
  }

  getConfigHistory(): Promise<ConfigHistoryModel> {
    return this.client.get<ConfigHistoryModel>(HISTORY_PATH)
  }

  restoreConfig(version: number, expectedVersion: number): Promise<void> {
    return this.client.post<void>(RESTORE_PATH, { version, expected_version: expectedVersion })
  }
}
```

- [ ] **Step 5: Update the repository**

Replace `ui/src/modules/config/data/repositories/ConfigRepositoryImpl.ts`

```ts
import type { ConfigRemoteDataSource } from '@/modules/config/data/datasources/ConfigRemoteDataSource'
import {
  toConfigChangesModel,
  toConfigSnapshot,
  toConfigVersions,
} from '@/modules/config/data/models/ConfigModel'
import type {
  ConfigChanges,
  ConfigSnapshot,
  ConfigVersion,
} from '@/modules/config/domain/entities/ScraperConfig'
import type { ConfigRepository } from '@/modules/config/domain/repositories/ConfigRepository'

export class ConfigRepositoryImpl implements ConfigRepository {
  private readonly dataSource: ConfigRemoteDataSource

  constructor(dataSource: ConfigRemoteDataSource) {
    this.dataSource = dataSource
  }

  async getConfig(): Promise<ConfigSnapshot> {
    return toConfigSnapshot(await this.dataSource.getConfig())
  }

  saveConfig(changes: ConfigChanges, version: number): Promise<void> {
    return this.dataSource.saveConfig(toConfigChangesModel(changes), version)
  }

  async getConfigHistory(): Promise<ConfigVersion[]> {
    return toConfigVersions(await this.dataSource.getConfigHistory())
  }

  restoreConfig(version: number, expectedVersion: number): Promise<void> {
    return this.dataSource.restoreConfig(version, expectedVersion)
  }
}
```

- [ ] **Step 6: Update and add the use cases**

Replace `ui/src/modules/config/domain/usecases/SaveConfigUseCase.ts`

```ts
import type { ConfigChanges } from '@/modules/config/domain/entities/ScraperConfig'
import type { ConfigRepository } from '@/modules/config/domain/repositories/ConfigRepository'

export class SaveConfigUseCase {
  private readonly repository: ConfigRepository

  constructor(repository: ConfigRepository) {
    this.repository = repository
  }

  execute(changes: ConfigChanges, version: number): Promise<void> {
    return this.repository.saveConfig(changes, version)
  }
}
```

Create `ui/src/modules/config/domain/usecases/GetConfigHistoryUseCase.ts`

```ts
import type { ConfigVersion } from '@/modules/config/domain/entities/ScraperConfig'
import type { ConfigRepository } from '@/modules/config/domain/repositories/ConfigRepository'

export class GetConfigHistoryUseCase {
  private readonly repository: ConfigRepository

  constructor(repository: ConfigRepository) {
    this.repository = repository
  }

  execute(): Promise<ConfigVersion[]> {
    return this.repository.getConfigHistory()
  }
}
```

Create `ui/src/modules/config/domain/usecases/RestoreConfigUseCase.ts`

```ts
import type { ConfigRepository } from '@/modules/config/domain/repositories/ConfigRepository'

export class RestoreConfigUseCase {
  private readonly repository: ConfigRepository

  constructor(repository: ConfigRepository) {
    this.repository = repository
  }

  execute(version: number, expectedVersion: number): Promise<void> {
    return this.repository.restoreConfig(version, expectedVersion)
  }
}
```

Replace `ui/src/modules/config/presentation/stores/configUseCases.ts`

```ts
import type { GetConfigHistoryUseCase } from '@/modules/config/domain/usecases/GetConfigHistoryUseCase'
import type { GetConfigUseCase } from '@/modules/config/domain/usecases/GetConfigUseCase'
import type { RestoreConfigUseCase } from '@/modules/config/domain/usecases/RestoreConfigUseCase'
import type { SaveConfigUseCase } from '@/modules/config/domain/usecases/SaveConfigUseCase'

export interface ConfigUseCases {
  getConfig: Pick<GetConfigUseCase, 'execute'>
  saveConfig: Pick<SaveConfigUseCase, 'execute'>
  getConfigHistory: Pick<GetConfigHistoryUseCase, 'execute'>
  restoreConfig: Pick<RestoreConfigUseCase, 'execute'>
}

let useCases: ConfigUseCases | null = null

export function provideConfigUseCases(next: ConfigUseCases): void {
  useCases = next
}

export function requireConfigUseCases(): ConfigUseCases {
  if (useCases === null) {
    throw new Error('Config use cases are not provided')
  }
  return useCases
}
```

In `ui/src/modules/config/routes.ts`, add the imports and provide the new use cases

```ts
import { GetConfigHistoryUseCase } from '@/modules/config/domain/usecases/GetConfigHistoryUseCase'
import { RestoreConfigUseCase } from '@/modules/config/domain/usecases/RestoreConfigUseCase'
```

```ts
provideConfigUseCases({
  getConfig: new GetConfigUseCase(repository),
  saveConfig: new SaveConfigUseCase(repository),
  getConfigHistory: new GetConfigHistoryUseCase(repository),
  restoreConfig: new RestoreConfigUseCase(repository),
})
```

- [ ] **Step 7: Replace the store**

Replace `ui/src/modules/config/presentation/stores/useConfigStore.ts`

```ts
import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  hasConfigChanges,
  toConfigChanges,
  type ConfigSnapshot,
  type ConfigValues,
  type ConfigVersion,
} from '@/modules/config/domain/entities/ScraperConfig'
import { requireConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'
import { toErrorMessage } from '@/shared/utils/errorMessage'
import type { LoadStatus } from '@/shared/utils/loadStatus'

const FALLBACK_ERROR_MESSAGE = 'Something went wrong. Try again.'

export const useConfigStore = defineStore('config', () => {
  const status = ref<LoadStatus>('idle')
  const values = ref<ConfigValues | null>(null)
  const snapshot = ref<ConfigSnapshot | null>(null)
  const history = ref<ConfigVersion[]>([])
  const errorMessage = ref<string | null>(null)
  const saveError = ref<string | null>(null)
  const historyError = ref<string | null>(null)
  const isSaving = ref(false)
  const isRestoring = ref(false)

  async function load(): Promise<void> {
    status.value = 'loading'
    errorMessage.value = null
    try {
      const next = await requireConfigUseCases().getConfig.execute()
      snapshot.value = next
      values.value = structuredClone(next.values)
      status.value = 'ready'
    } catch (error) {
      errorMessage.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      status.value = 'error'
    }
  }

  async function loadHistory(): Promise<void> {
    historyError.value = null
    try {
      history.value = await requireConfigUseCases().getConfigHistory.execute()
    } catch (error) {
      historyError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
    }
  }

  async function save(): Promise<boolean> {
    const current = values.value
    const loaded = snapshot.value
    if (current === null || loaded === null || loaded.isStale) {
      return false
    }
    const changes = toConfigChanges(current, loaded.values)
    if (!hasConfigChanges(changes)) {
      return true
    }
    isSaving.value = true
    saveError.value = null
    try {
      await requireConfigUseCases().saveConfig.execute(changes, loaded.version)
      await Promise.all([load(), loadHistory()])
      return true
    } catch (error) {
      saveError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      return false
    } finally {
      isSaving.value = false
    }
  }

  async function restore(version: number): Promise<boolean> {
    const loaded = snapshot.value
    if (loaded === null || loaded.isStale) {
      return false
    }
    isRestoring.value = true
    saveError.value = null
    try {
      await requireConfigUseCases().restoreConfig.execute(version, loaded.version)
      await Promise.all([load(), loadHistory()])
      return true
    } catch (error) {
      saveError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      return false
    } finally {
      isRestoring.value = false
    }
  }

  return {
    status,
    values,
    snapshot,
    history,
    errorMessage,
    saveError,
    historyError,
    isSaving,
    isRestoring,
    load,
    loadHistory,
    save,
    restore,
  }
})
```

- [ ] **Step 8: Run the tests**

Run: `cd ui && bunx vitest run src/modules/config/presentation/stores`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add ui/src/modules/config
git commit -m "feat: add config history and restore to the store"
```

---

## Task 10: Build the settings components

**Files:**
- Create: `ListInput.vue`, `LineListInput.vue`, `FilterFields.vue`, `SiteSettings.vue` in `ui/src/modules/config/presentation/components/`

These components are thin UI over the tested domain functions. Task 15 checks them in the running app

- [ ] **Step 1: Create the comma list input**

Create `ui/src/modules/config/presentation/components/ListInput.vue`

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { Input } from '@/shared/components/ui/input'
import { parseKeywords } from '@/shared/utils/parseKeywords'

const props = defineProps<{
  id: string
  modelValue: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [items: string[]]
}>()

const text = computed({
  get: () => props.modelValue.join(', '),
  set: (next: string) => emit('update:modelValue', parseKeywords(next)),
})
</script>

<template>
  <Input :id="id" v-model="text" />
</template>
```

- [ ] **Step 2: Create the line list input**

API locations such as `Jakarta, Indonesia` hold commas, so they need one value per line. The value updates on `change`, so typing a new line is not interrupted

Create `ui/src/modules/config/presentation/components/LineListInput.vue`

```vue
<script setup lang="ts">
defineProps<{
  id: string
  modelValue: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [items: string[]]
}>()

function update(event: Event): void {
  const text = (event.target as HTMLTextAreaElement).value
  const items = text
    .split('\n')
    .map((item) => item.trim())
    .filter((item) => item !== '')
  emit('update:modelValue', items)
}
</script>

<template>
  <textarea
    :id="id"
    :value="modelValue.join('\n')"
    rows="3"
    class="w-full min-w-0 rounded-md border border-line-strong bg-surface px-3 py-2 text-body text-ink outline-none transition-colors duration-150 focus-visible:border-accent focus-visible:focus-ring disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-ink-muted"
    @change="update"
  />
</template>
```

- [ ] **Step 3: Create the filter inputs**

Create `ui/src/modules/config/presentation/components/FilterFields.vue`

```vue
<script setup lang="ts">
import type { FilterSetting } from '@/modules/config/domain/entities/ScraperConfig'
import ListInput from '@/modules/config/presentation/components/ListInput.vue'
import { Label } from '@/shared/components/ui/label'

const props = defineProps<{
  idPrefix: string
  modelValue: FilterSetting
}>()

const emit = defineEmits<{
  'update:modelValue': [filter: FilterSetting]
}>()

function change(changes: Partial<FilterSetting>): void {
  emit('update:modelValue', { ...props.modelValue, ...changes })
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-col gap-2">
      <Label :for="`${idPrefix}-location`">Locations, separated by commas</Label>
      <ListInput
        :id="`${idPrefix}-location`"
        :model-value="modelValue.location"
        @update:model-value="change({ location: $event })"
      />
    </div>
    <div class="flex flex-col gap-2">
      <Label :for="`${idPrefix}-employment`">Employment types, separated by commas</Label>
      <ListInput
        :id="`${idPrefix}-employment`"
        :model-value="modelValue.employmentType"
        @update:model-value="change({ employmentType: $event })"
      />
    </div>
    <div class="flex flex-col gap-2">
      <Label :for="`${idPrefix}-work`">Work types, separated by commas</Label>
      <ListInput
        :id="`${idPrefix}-work`"
        :model-value="modelValue.workType"
        @update:model-value="change({ workType: $event })"
      />
    </div>
  </div>
</template>
```

- [ ] **Step 4: Create the site settings**

Create `ui/src/modules/config/presentation/components/SiteSettings.vue`

```vue
<script setup lang="ts">
import {
  EMPTY_FILTER,
  toDelaySeconds,
  toOptionalNumber,
  type ApiSetting,
  type SiteChanges,
  type SiteSetting,
} from '@/modules/config/domain/entities/ScraperConfig'
import FilterFields from '@/modules/config/presentation/components/FilterFields.vue'
import LineListInput from '@/modules/config/presentation/components/LineListInput.vue'
import ListInput from '@/modules/config/presentation/components/ListInput.vue'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

const GLOBAL_VALUE_HINT = 'Global'

const props = defineProps<{
  site: SiteSetting
  defaultFields: string[]
}>()

const emit = defineEmits<{
  update: [site: SiteSetting]
}>()

function change(changes: SiteChanges): void {
  emit('update', { ...props.site, ...changes })
}

function changeApi(changes: Partial<ApiSetting>): void {
  if (props.site.api !== null) {
    change({ api: { ...props.site.api, ...changes } })
  }
}

function changeDelayMin(value: string | number): void {
  const max = props.site.api?.delaySeconds?.[1] ?? null
  changeApi({ delaySeconds: toDelaySeconds(toOptionalNumber(value), max) })
}

function changeDelayMax(value: string | number): void {
  const min = props.site.api?.delaySeconds?.[0] ?? null
  changeApi({ delaySeconds: toDelaySeconds(min, toOptionalNumber(value)) })
}
</script>

<template>
  <div class="flex flex-col gap-2 border-b border-line-strong pb-3">
    <div class="flex items-center gap-3">
      <Checkbox
        :id="`config-site-${site.name}`"
        :model-value="site.isEnabled"
        @update:model-value="change({ isEnabled: $event === true })"
      />
      <Label :for="`config-site-${site.name}`" class="w-28">{{ site.name }}</Label>
      <Input
        :model-value="site.limit ?? ''"
        type="number"
        min="1"
        class="w-24"
        :aria-label="`${site.name} limit`"
        :placeholder="GLOBAL_VALUE_HINT"
        @update:model-value="change({ limit: toOptionalNumber($event) })"
      />
    </div>
    <details>
      <summary class="cursor-pointer text-body-sm text-ink-muted">More settings</summary>
      <div class="mt-3 flex flex-col gap-4">
        <div class="flex flex-col gap-2">
          <Label :for="`${site.name}-max-age`">Max job age in hours</Label>
          <Input
            :id="`${site.name}-max-age`"
            :model-value="site.maxAgeHours ?? ''"
            type="number"
            min="1"
            :placeholder="GLOBAL_VALUE_HINT"
            @update:model-value="change({ maxAgeHours: toOptionalNumber($event) })"
          />
        </div>
        <div class="flex flex-col gap-3">
          <div class="flex items-center gap-3">
            <Checkbox
              :id="`${site.name}-own-filter`"
              :model-value="site.filter !== null"
              @update:model-value="change({ filter: $event === true ? EMPTY_FILTER : null })"
            />
            <Label :for="`${site.name}-own-filter`">
              Use its own filter. Leave the fields empty for no filter
            </Label>
          </div>
          <FilterFields
            v-if="site.filter !== null"
            :id-prefix="site.name"
            :model-value="site.filter"
            @update:model-value="change({ filter: $event })"
          />
        </div>
        <div class="flex flex-col gap-3">
          <div class="flex items-center gap-3">
            <Checkbox
              :id="`${site.name}-own-fields`"
              :model-value="site.fields !== null"
              @update:model-value="change({ fields: $event === true ? defaultFields : null })"
            />
            <Label :for="`${site.name}-own-fields`">Use its own job fields</Label>
          </div>
          <ListInput
            v-if="site.fields !== null"
            :id="`${site.name}-fields`"
            :aria-label="`${site.name} job fields`"
            :model-value="site.fields"
            @update:model-value="change({ fields: $event })"
          />
        </div>
        <div v-if="site.api !== null" class="flex flex-col gap-3">
          <div class="flex items-center gap-3">
            <Checkbox
              :id="`${site.name}-api-enabled`"
              :model-value="site.api.isEnabled"
              @update:model-value="changeApi({ isEnabled: $event === true })"
            />
            <Label :for="`${site.name}-api-enabled`">Use the API</Label>
          </div>
          <div class="flex items-center gap-3">
            <Checkbox
              :id="`${site.name}-api-country`"
              :model-value="site.api.isCountryWide"
              @update:model-value="changeApi({ isCountryWide: $event === true })"
            />
            <Label :for="`${site.name}-api-country`">Also search the whole country</Label>
          </div>
          <div class="flex flex-col gap-2">
            <Label :for="`${site.name}-api-locations`">API locations, one per line</Label>
            <LineListInput
              :id="`${site.name}-api-locations`"
              :model-value="site.api.locations"
              @update:model-value="changeApi({ locations: $event })"
            />
          </div>
          <div class="flex items-center gap-3">
            <Label :for="`${site.name}-api-delay-min`">Delay in seconds, min and max</Label>
            <Input
              :id="`${site.name}-api-delay-min`"
              :model-value="site.api.delaySeconds?.[0] ?? ''"
              type="number"
              min="0"
              step="0.5"
              class="w-24"
              @update:model-value="changeDelayMin"
            />
            <Input
              :model-value="site.api.delaySeconds?.[1] ?? ''"
              type="number"
              min="0"
              step="0.5"
              class="w-24"
              :aria-label="`${site.name} max delay`"
              @update:model-value="changeDelayMax"
            />
          </div>
        </div>
      </div>
    </details>
  </div>
</template>
```

- [ ] **Step 5: Commit**

Do not run `type-check` yet. `ConfigPage.vue` still uses the old types until Task 11

```bash
git add ui/src/modules/config/presentation/components
git commit -m "feat: add site and filter settings components"
```

---

## Task 11: Update the page and add history

**Files:**
- Create: `ui/src/modules/config/presentation/components/ConfigHistory.vue`
- Modify: `ui/src/modules/config/presentation/pages/ConfigPage.vue`

- [ ] **Step 1: Create the history list**

Restore needs a second click, because there is no dialog component in `shared/components/ui`

Create `ui/src/modules/config/presentation/components/ConfigHistory.vue`

```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import { Button } from '@/shared/components/ui/button'

const RESTORED_MESSAGE = 'Version restored'

const store = useConfigStore()
const pendingVersion = ref<number | null>(null)
const isLocked = computed(() => store.isRestoring || (store.snapshot?.isStale ?? true))

function toLocalTime(timestamp: string): string {
  return new Date(timestamp).toLocaleString()
}

async function confirmRestore(version: number): Promise<void> {
  pendingVersion.value = null
  if (await store.restore(version)) {
    toast.success(RESTORED_MESSAGE)
  }
}
</script>

<template>
  <section aria-labelledby="config-history-title" class="flex flex-col gap-3">
    <h2 id="config-history-title" class="text-body-sm font-semibold">Older versions</h2>
    <p v-if="store.historyError" role="alert" class="text-body-sm">{{ store.historyError }}</p>
    <p v-else-if="store.history.length === 0" class="text-body-sm text-ink-muted">
      No older versions yet
    </p>
    <ul v-else class="flex flex-col gap-3">
      <li
        v-for="entry in store.history"
        :key="entry.version"
        class="flex flex-wrap items-center justify-between gap-3 border-b border-line-strong pb-3"
      >
        <div class="flex min-w-0 flex-col">
          <span class="text-body-sm font-semibold">
            Version {{ entry.version }}, {{ toLocalTime(entry.updatedAt) }}, by
            {{ entry.updatedBy }}
          </span>
          <span class="text-body-sm text-ink-muted">{{ entry.keywords.join(', ') }}</span>
          <span class="text-body-sm text-ink-muted">{{ entry.enabledSites.join(', ') }}</span>
        </div>
        <div v-if="pendingVersion === entry.version" class="flex gap-2">
          <Button type="button" :disabled="isLocked" @click="confirmRestore(entry.version)">
            Confirm restore
          </Button>
          <Button type="button" variant="secondary" @click="pendingVersion = null">Cancel</Button>
        </div>
        <Button
          v-else
          type="button"
          variant="secondary"
          :disabled="isLocked"
          @click="pendingVersion = entry.version"
        >
          Restore
        </Button>
      </li>
    </ul>
  </section>
</template>
```

- [ ] **Step 2: Replace the page**

Replace `ui/src/modules/config/presentation/pages/ConfigPage.vue`

```vue
<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import {
  toOptionalNumber,
  type SiteSetting,
} from '@/modules/config/domain/entities/ScraperConfig'
import ConfigHistory from '@/modules/config/presentation/components/ConfigHistory.vue'
import FilterFields from '@/modules/config/presentation/components/FilterFields.vue'
import ListInput from '@/modules/config/presentation/components/ListInput.vue'
import SiteSettings from '@/modules/config/presentation/components/SiteSettings.vue'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Skeleton } from '@/shared/components/ui/skeleton'

const SAVED_MESSAGE = 'Config saved'

const store = useConfigStore()
const isStale = computed(() => store.snapshot?.isStale ?? true)
const savedAt = computed(() =>
  store.snapshot === null ? '' : new Date(store.snapshot.updatedAt).toLocaleString(),
)

function updateSite(next: SiteSetting): void {
  if (store.values !== null) {
    store.values.sites = store.values.sites.map((site) => (site.name === next.name ? next : site))
  }
}

async function save(): Promise<void> {
  if (await store.save()) {
    toast.success(SAVED_MESSAGE)
  }
}

onMounted(() => {
  void store.load()
  void store.loadHistory()
})
</script>

<template>
  <div class="flex flex-col gap-6">
    <h1 class="text-title">Config</h1>
    <Skeleton v-if="store.status === 'loading'" class="h-40" />
    <p v-else-if="store.status === 'error'" role="alert">{{ store.errorMessage }}</p>
    <template v-else-if="store.values">
      <form class="flex flex-col gap-4" @submit.prevent="save">
        <p class="text-body-sm text-ink-muted">
          Version {{ store.snapshot?.version }}, saved {{ savedAt }} by
          {{ store.snapshot?.updatedBy }}. Changes apply from the next run
        </p>
        <p v-if="isStale" class="text-body-sm text-ink-muted">
          The scraper is busy, so these values may be out of date. Saving is off until it is free
        </p>
        <fieldset :disabled="isStale" class="flex min-w-0 flex-col gap-4 border-0 p-0">
          <div class="flex flex-col gap-2">
            <Label for="keywords">Keywords, separated by commas</Label>
            <ListInput id="keywords" v-model="store.values.keywords" />
          </div>
          <div class="flex flex-col gap-2">
            <Label for="limit">Limit per site</Label>
            <Input
              id="limit"
              :model-value="store.values.limit ?? ''"
              type="number"
              min="1"
              @update:model-value="store.values!.limit = toOptionalNumber($event)"
            />
          </div>
          <div class="flex flex-col gap-2">
            <Label for="max-age">Max job age in hours</Label>
            <Input
              id="max-age"
              :model-value="store.values.maxAgeHours ?? ''"
              type="number"
              min="1"
              @update:model-value="store.values!.maxAgeHours = toOptionalNumber($event)"
            />
          </div>
          <div class="flex flex-col gap-3">
            <p class="text-body-sm font-semibold">Global filter</p>
            <FilterFields id-prefix="global" v-model="store.values.filter" />
          </div>
          <div class="flex flex-col gap-2">
            <Label for="default-fields">Job fields, separated by commas</Label>
            <ListInput id="default-fields" v-model="store.values.defaultFields" />
          </div>
          <fieldset class="flex flex-col gap-3">
            <legend class="text-body-sm font-semibold">Sites</legend>
            <SiteSettings
              v-for="site in store.values.sites"
              :key="site.name"
              :site="site"
              :default-fields="store.values.defaultFields"
              @update="updateSite"
            />
          </fieldset>
        </fieldset>
        <p v-if="store.saveError" role="alert" class="text-body-sm">{{ store.saveError }}</p>
        <div>
          <Button type="submit" :disabled="store.isSaving || isStale">Save</Button>
        </div>
      </form>
      <ConfigHistory />
    </template>
  </div>
</template>
```

- [ ] **Step 3: Check types and tests**

Run: `cd ui && bun run type-check`
Expected: exit 0

Run: `cd ui && bunx vitest run`
Expected: PASS

Run: `cd ui && bun run build`
Expected: build succeeds

- [ ] **Step 4: Format**

Run: `cd ui && bunx prettier --write src/modules/config`
Expected: files formatted

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules/config
git commit -m "feat: edit all job settings and restore versions on /config"
```

---

## Task 12: Trim `config.yaml` and update deployment

**Files:**
- Modify: `config.yaml`, `docker-compose.yml`, `docker-compose.dev.yml`, `.env.example`, `.env`, `.gitignore`, `.github/workflows/deploy.yml`, `prompts/scrape-and-post.md`, `scripts/run_dev.sh`, `scripts/run_prod.sh`, `scripts/test-locally.sh`, `scripts/test_cron_dev.sh`, `tests/test_seed_settings.py`
- Delete: `config.dev.patch.yaml`, `config.dev.patch.yaml.example`, `config-backups/`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_seed_settings.py`

```python
def test_config_file_holds_no_job_settings():
    config = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())

    assert set(config) == {"concurrency", "output_dir", "bot"}
```

Run: `.venv/bin/python -m pytest tests/test_seed_settings.py -q`
Expected: FAIL

- [ ] **Step 2: Trim `config.yaml`**

Replace `config.yaml`

```yaml
# Machine settings, baked into the images. Job settings live in Mongo: edit them at /config.
# The proxy lives in the SCRAPER_PROXY_URL env var.
concurrency: 2
output_dir: output

bot:
  schedule: "0 11 * * *"
  max_chars: 1900
  message_template: |
    ## {title}
    {company} | {location}

    **Details**
    Link: [link]({url})
    Source: {site}
    Diposting: {posted_date}

  # Use this inside "message_template" to display the requirements
  # **Requirements**:
  # {requirements}
```

Run: `.venv/bin/python -m pytest tests/test_seed_settings.py -q`
Expected: PASS

- [ ] **Step 3: Remove the dev patch**

Before deleting, read the owner's dev values in `config.dev.patch.yaml`. Task 15 sets them on `/config`. Step 1 of Task 0 must be done first

```bash
git rm config.dev.patch.yaml config.dev.patch.yaml.example
rmdir config-backups
```

In `.gitignore`, delete the `config-backups/` line, the `config.yaml.bak.*` line, and the `config.dev.patch.yaml` line with its comment above

- [ ] **Step 4: Pass the proxy env var**

Pass-through form keeps unset as unset and empty as empty. `docker compose config` shows `null` for unset

In `docker-compose.yml`, in `scraper-mcp`, add to `environment`

```yaml
      - SCRAPER_PROXY_URL # no default on purpose: unset stops scrapes, empty means direct connection
```

In the commented `scraper` service, change `#     - PROXY_URL=${PROXY_URL:-}` to

```yaml
  #     - SCRAPER_PROXY_URL
  #     - MONGO_URI=mongodb://${MONGO_ROOT_USER:-admin}:${MONGO_ROOT_PASSWORD}@mongo:27017
```

- [ ] **Step 5: Update the dev overlay**

Replace `docker-compose.dev.yml`

```yaml
services:

  # Delete this to activate the cron schedule job.
  # Also mounts full config (base removed it; dev needs it, prod uses image-baked config).
  bot:
    entrypoint: ["sleep"]
    command: ["infinity"]
    volumes:
      - ./config.yaml:/workspace/config.yaml:ro

  # override: run as the host user so output/ui-runs stays writable; local access only
  scraper-ui:
    user: "${UI_UID:-1001}:${UI_GID:-1001}"
    ports:
      - "127.0.0.1:8090:8090"
    environment:
      - UI_ENV=dev
      - UI_MCP_URL=http://scraper-mcp:8080/mcp
```

- [ ] **Step 6: Update the env files**

In `.env.example`, replace the `PROXY_URL` block

```bash
# SOCKS5/HTTP proxy for scraper-mcp. Required: leave it empty for a direct connection.
# When this line is missing, scrapes stop with an error.
# Example: socks5://host.docker.internal:1080
SCRAPER_PROXY_URL=
```

and change the `UI_UID` comment to

```bash
# Host user for scraper-ui in dev, so it can write output/ui-runs. scripts/run_dev.sh sets
```

Add `SCRAPER_PROXY_URL=` to the local `.env`. Do not print or commit `.env`

- [ ] **Step 7: Require the var in deploy**

In `.github/workflows/deploy.yml`, in the `Deploy scraper-mcp` step, add `SCRAPER_PROXY_URL` to `envs`

```yaml
          envs: MCP_IMAGE,MONGO_ROOT_USER,MONGO_ROOT_PASSWORD,MONGO_DB_NAME,MONGO_COLLECTION_NAME,MCP_BIND_HOST,SCRAPER_PROXY_URL
```

Add this right after `set -euo pipefail` in that script. A missing GitHub var arrives as an empty string, which would mean direct connection, so prod needs its own check

```bash
            : "${SCRAPER_PROXY_URL:?Set the SCRAPER_PROXY_URL GitHub variable}"
```

Add to the step's `env` map

```yaml
          SCRAPER_PROXY_URL: ${{ vars.SCRAPER_PROXY_URL }}
```

- [ ] **Step 8: Update `scripts/run_dev.sh`**

Replace the part from `# Start the dev environment` through `mkdir -p "$REPO_ROOT/config-backups"`

```bash
# Start the dev environment. Job settings come from this machine's Mongo.
# First run: ./seed.sh job-settings
#
# Usage:
#   ./scripts/run_dev.sh           # mcp + bot + ui
#   ./scripts/run_dev.sh mcp       # MCP server only
#   ./scripts/run_dev.sh bot       # bot only
#   ./scripts/run_dev.sh ui        # MCP server + UI at http://127.0.0.1:8090

# --- config ---
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_BASE="docker-compose.yml"
COMPOSE_ENV="docker-compose.dev.yml"
ARG="${1:-all}"

# --- ui file access ---
# scraper-ui writes host-owned output/ui-runs, so it runs as the host user in dev.
export UI_UID="$(id -u)" UI_GID="$(id -g)"
```

Change the last two lines

```bash
echo "==> Starting dev environment (services: ${ARG})..."
docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" $PROFILES up --build -d
```

- [ ] **Step 9: Update `scripts/run_prod.sh`**

Change the header comment to `# Start the prod environment with the proxy on.` and add after `ARG="${1:-all}"`

```bash
export SCRAPER_PROXY_URL="socks5://${PROXY_HOST}:${PROXY_PORT}"
```

- [ ] **Step 10: Update the test scripts**

In `scripts/test-locally.sh` and `scripts/test_cron_dev.sh`, delete the `MERGED_CONFIG=` line, the `yq` guard block, and the merge block. In `scripts/test_cron_dev.sh`, also delete the `yq` line in the header comment and change the line `# One-shot dev test of the scrape → Discord post flow using the dev config overlay.` to `# One-shot dev test of the scrape → Discord post flow. Needs seeded job settings.`, and rewrite the next header line that mentions the merge to `# Starts mongo + scraper-mcp through the dev compose files.`

- [ ] **Step 11: Update the bot prompt**

In `prompts/scrape-and-post.md`, line 9, replace ``content filters from the bound `config.yaml`, and return aggregated results.`` with

```text
content filters from the job settings in Mongo, and return aggregated results.
```

- [ ] **Step 12: Verify the compose result**

Run: `docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile mcp --profile ui config | grep -n SCRAPER_PROXY_URL`
Expected: `SCRAPER_PROXY_URL: ""`

Run: `bash -n scripts/run_dev.sh scripts/run_prod.sh scripts/test-locally.sh scripts/test_cron_dev.sh`
Expected: no output

Run: `grep -rn "config.dev\|MERGED_CONFIG\|config-backups" scripts docker-compose*.yml Dockerfile .gitignore .env.example --include='*' | grep -v manage_tui`
Expected: only `scripts/environments.yaml`, which Task 13 fixes

- [ ] **Step 13: Commit**

```bash
git add config.yaml docker-compose.yml docker-compose.dev.yml .env.example .gitignore \
  .github/workflows/deploy.yml prompts/scrape-and-post.md scripts/run_dev.sh scripts/run_prod.sh \
  scripts/test-locally.sh scripts/test_cron_dev.sh tests/test_seed_settings.py
git commit -m "feat: drop job settings and the dev patch from config files"
```

---

## Task 13: Update the Docker manager TUI

**Files:**
- Modify: `scripts/environments.yaml`, `scripts/manage.py`, `scripts/manage_tui/__init__.py`, `scripts/manage_tui/model.py`, `scripts/manage_tui/commands.py`, `scripts/manage_tui/config_view.py`, `scripts/manage_tui/app.py`

The TUI has no test suite. Step 7 checks it with a direct import

- [ ] **Step 1: Remove the merge from the manifest**

In `scripts/environments.yaml`, delete the two `config_merge` comment lines, the Shape line, the dev `config_merge:` block, and the prod `config_merge: null` line. Set the descriptions

```yaml
    description: "Local dev — direct connection"
```

```yaml
    description: "Production — SOCKS5 proxy"
```

- [ ] **Step 2: Remove the merge from the model**

In `scripts/manage_tui/model.py`, delete the `ConfigMerge` dataclass, the `config_merge` field, the `config_merge=...` line in `_parse_environment`, and `_parse_merge`

- [ ] **Step 3: Update the commands**

In `scripts/manage_tui/commands.py`

Change the module docstring line to `Each action is one command today.`, and keep the sequence type. Delete `merge_command`. Change the `start` branch

```python
    if action == "start":
        return [
            Command(
                base
                + ["--progress", "plain"]
                + _profile_flags(scope, profiles)
                # --quiet-pull: layer-pull progress is carriage-return spam with
                # no newlines; silencing it keeps the log clean (and avoids
                # multi-MB no-newline "lines"). --progress plain handles build.
                + ["up", "--build", "--quiet-pull", "-d"]
            )
        ]
```

Change the top of `_base`. The local `.env` holds the dev value, so an environment with a proxy must set the var itself

```python
def _base(env: Environment) -> list[str]:
    cmd = ["env", f"{PROXY_ENV_VAR}={env.proxy.check_url}"] if env.proxy else []
    cmd += ["docker", "compose"]
```

Add near the imports

```python
PROXY_ENV_VAR = "SCRAPER_PROXY_URL"
```

Change the `Command` docstring so it no longer mentions the `yq` merge

```python
    """One process invocation.

    stdout_path mirrors a shell `> file` redirect. The runner opens that file
    for the child's stdout; the preview renders the ` > file` suffix so what
    the user sees matches what runs.
    """
```

- [ ] **Step 4: Replace the config view**

In `scripts/manage_tui/config_view.py`, replace the module docstring, the constants, `ConfigSummary`, and `load_config_summary`. Delete `_deep_merge`. Keep `parse_env`, `masked_env`, and `_mask`

```python
"""Read-only config display: .env (masked) + machine settings.

Job settings live in Mongo and are edited at /config, so this view does not
show them. Site names come from the seed file: they only change there.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .model import REPO_ROOT, Environment

ENV_PATH = REPO_ROOT / ".env"
SEED_PATH = REPO_ROOT / "seeds" / "job_settings.yaml"

PROXY_ENV_KEY = "SCRAPER_PROXY_URL"
MASK_KEYS = {"MONGO_ROOT_PASSWORD", "DISCORD_BOT_TOKEN", PROXY_ENV_KEY}
SHOWN_ENV_KEYS = (
    "MONGO_ROOT_USER",
    "MONGO_ROOT_PASSWORD",
    "MONGO_DB_NAME",
    "MONGO_COLLECTION_NAME",
    "DISCORD_BOT_TOKEN",
    "DISCORD_CHANNEL_ID",
    PROXY_ENV_KEY,
)


@dataclass(frozen=True)
class ConfigSummary:
    source_label: str
    site_names: list[str]
    proxy: str
    mongo_db: str
    mongo_collection: str
```

```python
def load_config_summary(env: Environment, env_vars: dict[str, str]) -> ConfigSummary:
    seed = yaml.safe_load(SEED_PATH.read_text()) or {}
    return ConfigSummary(
        source_label=f"{env.name} (job settings in Mongo, edit at /config)",
        site_names=sorted(seed.get("sites") or {}),
        proxy=_proxy_label(env, env_vars),
        mongo_db=env_vars.get("MONGO_DB_NAME", "job_scraper"),
        mongo_collection=env_vars.get("MONGO_COLLECTION_NAME", "scrape_runs"),
    )


def _proxy_label(env: Environment, env_vars: dict[str, str]) -> str:
    if env.proxy is not None:
        return env.proxy.check_url
    value = env_vars.get(PROXY_ENV_KEY)
    if value is None:
        return f"({PROXY_ENV_KEY} not set in .env: scrapes will stop)"
    return "(disabled)" if value == "(empty)" else value
```

- [ ] **Step 5: Update the app**

In `scripts/manage_tui/app.py`

Change `_row_label`

```python
    def _row_label(self, scope: str) -> str:
        if scope == "bot" and self.env.name == "dev":
            return "bot (idles in dev)"
        return scope
```

In `_scrape_widgets`, change the button line

```python
        children += [Button(site, id=f"scrape-{site}") for site in cfg.site_names]
```

In `_render_summary`, delete the `keywords` and `sites` lines

- [ ] **Step 6: Update the docstrings**

In `scripts/manage.py`, change the docstring sentence to

```text
command before it runs. Read-only over config: it loads .env, the compose
files, and the seed file for display, never writing back.
```

In `scripts/manage_tui/__init__.py`, change the `config_view` line to

```text
    config_view  parse .env (masked) -> display summary
```

- [ ] **Step 7: Check the modules load**

Run:

```bash
.venv/bin/python -c "import sys; sys.path.insert(0, 'scripts'); from manage_tui.model import load_manifest; from manage_tui.config_view import load_config_summary; from manage_tui.commands import build_sequence; m = load_manifest(); print(load_config_summary(m.environments['dev'], {'SCRAPER_PROXY_URL': '(empty)'})); print(build_sequence(m.environments['prod'], 'all', 'start', {'mcp': ['scraper-mcp']})[0].preview())"
```

Expected: the summary shows `proxy='(disabled)'`, and the prod preview starts with `env SCRAPER_PROXY_URL=socks5://localhost:1080 docker compose`

Run: `.venv/bin/python -m ruff check scripts scraper mcp_server ui_server tests`
Expected: no errors. If ruff is not in `.venv`, use `uvx ruff check` with the same paths

- [ ] **Step 8: Commit**

```bash
git add scripts/environments.yaml scripts/manage_tui/model.py scripts/manage_tui/commands.py \
  scripts/manage_tui/config_view.py scripts/manage_tui/app.py
git commit -m "feat: drop the config merge from the Docker manager"
```

Commit `scripts/manage.py` and `scripts/manage_tui/__init__.py` only if the owner has settled the earlier uncommitted edits in those files from Task 0

---

## Task 14: Update the docs

**Files:**
- Modify: `README.md`, `docs/configuration.md`, `docs/mcp.md`, `docs/runbook.md`, `docs/deploy.md`

- [ ] **Step 1: Update `README.md`**

Line 11: replace with `Driven by job settings in Mongo (keywords, sites, filters), edited at /config. The bot schedule stays in config.yaml.`

In the setup table, replace the `.env.example` row's `PROXY_URL` with `SCRAPER_PROXY_URL`, and delete the `config.dev.patch.yaml.example` row

In `# Seed reference data`, replace `Seeds are idempotent — drop + recreate each run.` with

```markdown
`./seed.sh job-settings` runs only the job settings seed, and `./seed.sh wilayah` runs only the area codes.

The wilayah seed drops and recreates its collection on each run. The job settings seed only inserts when the document is missing, so it never overwrites your edits. It needs `.venv`, or a Python path in `SCRAPER_PYTHON`.
```

In `# SSH tunnel`, replace the sentence that starts `` `config.yaml` has `proxy: socks5://localhost:1080` `` so it starts with `` `SCRAPER_PROXY_URL` is `socks5://localhost:1080` in prod ``

Replace the whole `# Config: config.yaml + the dev patch` section, up to `# How the filter works`, with

```markdown
# Config: Mongo, config.yaml, and the proxy var

Settings live in three places, by how they change

| Place | Holds | Change it |
| --- | --- | --- |
| `job_settings` collection | `keywords`, `limit`, `max_age_hours`, `filter`, `default_fields`, `sites` | `/config` page, applies from the next run |
| `SCRAPER_PROXY_URL` env var | Proxy URL. Empty means direct connection. Not set stops scrapes | `.env` in dev, GitHub variable in prod |
| `config.yaml` | `concurrency`, `output_dir`, `bot.*` | Edit and rebuild the images |

Each host's Mongo has its own document, so dev and prod differ without a patch file. A new environment needs one seed

    ./seed.sh job-settings

`seeds/job_settings.yaml` is only the first version. After seeding, `/config` is the source. `url_template` can change only through the `update_config` MCP tool

The last 20 versions stay in `job_settings_history`, and `/config` can restore any of them

> **Note on `bot.schedule`:** the crontab is generated from `config.yaml` at
> **image build time** (Dockerfile `bot` stage). Changing `bot.schedule` requires
> a rebuild and redeploy — editing `config.yaml` on a running container has no
> effect.
```

In `# How the filter works`, change `` `filter:` in `config.yaml` runs `` to `` The `filter` job setting runs ``

In the UI notes, replace the two lines about dev config edits and read-only prod with

```markdown
- Config saves go through `scraper-mcp` into Mongo. Saving is off while a scrape runs, because MCP is busy then
- Prod is public through Caddy with one password
```

In the scraping prompt section, change `using `config.yaml` filters` to `using the job settings filters`

- [ ] **Step 2: Update `docs/configuration.md`**

Replace the intro paragraph with

```markdown
Job settings live in the `job_settings` Mongo collection, one document per
environment. Edit them at `/config`, or with the `update_config` MCP tool.
`config.yaml` holds `concurrency`, `output_dir`, and `bot`. The proxy lives in
the `SCRAPER_PROXY_URL` env var.

`scraper/config_loader.py::parse` validates all of them into an `AppConfig`
dataclass. A malformed value raises `ConfigError`. A save with a malformed value
changes nothing, and a run with one aborts.

This page documents every key the loader recognizes. For filter semantics
specifically, see [`filters.md`](filters.md).
```

Under `## Top-level keys`, replace the code block's heading text by adding above it

```markdown
The examples below show the keys as YAML, which is the format of
`seeds/job_settings.yaml`. `concurrency` and `output_dir` go in `config.yaml`,
and the rest are job settings.
```

Replace the content from `## Proxy configuration` through the end of `### Disable proxy` so it opens with

````markdown
## Proxy configuration

Route HTTP requests through a proxy server. Useful for bypassing datacenter IP blocks by using residential IPs.

```bash
SCRAPER_PROXY_URL="socks5://localhost:1080"
```

The var must be set. When it is not, `scrape_jobs` returns `ok: false` and says so. Set it to empty for a direct connection. This stops a missing prod var from turning the proxy off without anyone noticing.
````

Keep `### Supported proxy formats`, `### Common setup: SSH tunnel`, and `### Docker considerations`, change their `config.yaml` examples to set `SCRAPER_PROXY_URL`, and delete `### Environment variable override` and `### Disable proxy`

Replace the content of `## Live editing via MCP` with

```markdown
The `/config` page is the normal way to change job settings. The MCP server
also exposes `update_config`. See [`mcp.md`](mcp.md) for the tool catalog and
patch shape.

Every save is validated through this same loader first. An invalid patch
returns an error and changes nothing.
```

In `## Loading the resolved config`, change the example to

```python
from pathlib import Path

from scraper.job_settings import load_app_config, open_store

config = load_app_config(Path("config.yaml"), open_store())
```

- [ ] **Step 3: Update `docs/mcp.md`**

Replace the `get_config` section's text and example

````markdown
Read-only. Returns the job settings from Mongo, with their version.

**Args**: none.

**Returns**:

```json
{
  "version": 4,
  "updated_at": "2026-11-02T01:00:00+00:00",
  "updated_by": "ui",
  "settings": {
    "keywords": ["software engineer"],
    "limit": 2,
    "max_age_hours": 24,
    "filter": {"location": ["jakarta"]},
    "sites": {}
  }
}
```

Returns `{"error": "..."}` when Mongo is down or the document is missing.
````

Replace the `update_config` section, through `#### Required permissions`, with

````markdown
Write. Applies a patch to the job settings, validates the result, and keeps the old version in history.

**Args**:

```json
{ "patch": { }, "expected_version": 4, "source": "mcp" }
```

- `patch`: top-level keys are replaced whole. `sites` merges by site name. Each field of a site is replaced whole, so send the full `filter` or `api`. A `null` removes the key, so a site field goes back to the global value
- `expected_version`: optional. The version you read. A mismatch saves nothing
- `source`: `ui` or `mcp`. Kept with the version

Only job setting keys are allowed. `proxy` and `concurrency` are refused.

**Returns** (success):

```json
{ "ok": true, "version": 5, "updated_at": "...", "updated_by": "mcp", "settings": { } }
```

**Returns** (failure, nothing changed):

```json
{ "ok": false, "reason": "invalid", "message": "'limit' must be >= 1, got -5" }
```

`reason` is `invalid`, `conflict`, or `unavailable`.

### `get_config_history`

Read-only. Returns up to 20 older versions, newest first.

```json
{ "entries": [ { "version": 3, "updated_at": "...", "updated_by": "seed", "keywords": ["..."], "enabled_sites": ["upwork"] } ] }
```

### `restore_config`

Write. Makes an older version current. The restore creates a new version, so it can be undone.

**Args**: `version`, `expected_version`, and optional `source`.

**Returns**: same shape as `update_config`.
````

Keep the `#### Patch examples` section, and delete any example that relied on deep merging inside `filter`. Delete the `To roll back manually` line and `#### Required permissions` with its compose block

Change the Operational rules: step 3 to `Call update_config with that patch and the version from get_config`, and step 4 to use `message` in place of `error`

- [ ] **Step 4: Update `docs/runbook.md`**

Replace the `## Backup discipline` section with

```markdown
## Version history

Every save keeps the old version in `job_settings_history`, last 20 kept. To
roll back, use **Restore** on `/config`, or call `restore_config` with the
version from `get_config_history`. A restore creates a new version, so it can
be undone the same way.
```

- [ ] **Step 5: Update `docs/deploy.md`**

Change `## Changing config`: replace `Because everything is baked in:` with `Job settings live in Mongo. The rest is baked in:`, and replace the first table row with

```markdown
| Change keywords, limits, filters, sites | Edit at `/config`. Applies from the next run, no deploy |
| Change the proxy | Update the `SCRAPER_PROXY_URL` GitHub variable → redeploy |
```

Add at the end of `## Seeding reference data`

````markdown
### Seed job settings

Run this once on a fresh MongoDB, and before the first deploy that reads job settings. It only inserts when the document is missing.

```bash
MONGO_HOST=127.0.0.1 MONGO_PORT=<LOCAL_PORT> MONGO_ROOT_PASSWORD=<MONGO_ROOT_PASSWORD> ./seed.sh job-settings
```

Without this document, scrapes stop with a message that names this command.
````

Add this row to the table under `## Required GitHub variables`

```markdown
| `SCRAPER_PROXY_URL` | `deploy-mcp` | Required. Proxy URL for scrapes, such as `socks5://localhost:1080`. The deploy fails when it is missing or empty |
```

- [ ] **Step 6: Update the other docs and the tunnel example**

`docs/sites.md`, line 147

```markdown
3. Add an entry under `sites:` in `seeds/job_settings.yaml` with a `url_template`, then add the same entry to each environment with the `update_config` MCP tool. A site's `url_template` cannot be set from `/config`.
```

`docs/architecture.md`

- Line 30: add `get_config_history` and `restore_config` to the tool list
- Line 37: in the file tree, keep `config.yaml`, and add `seeds/job_settings.yaml` next to it
- Line 139: change the paragraph to say `update_config` and `restore_config` are the mutating tools, and that both validate with the same parser before writing to Mongo
- Line 147: change the end to ``add the `sites.<name>` entry to `seeds/job_settings.yaml` and to each environment with `update_config` ``

`docs/filters.md`, line 3: change ``The `filter:` block in `config.yaml` drops jobs`` to ``The `filter` job setting drops jobs``

`docs/orchestration.md`, line 19: change `reads config.yaml` to `reads Mongo`, keeping the box width. Line 124 stays, because `bot:` stays in `config.yaml`

`scripts/ssh-tunnel.sh.example`

- Line 8: change ``from config.yaml`` to ``from SCRAPER_PROXY_URL``
- Line 33: change the comment to `# Check this against SCRAPER_PROXY_URL`

- [ ] **Step 7: Check for leftovers**

Run: `grep -rnE "config\.dev\.patch|/tmp/config\.dev|config-backups|PROXY_URL|config\.yaml\.bak" README.md docs/*.md | grep -v SCRAPER_PROXY_URL`
Expected: no output

- [ ] **Step 8: Commit**

Add `scripts/ssh-tunnel.sh.example` only if the owner has settled the earlier uncommitted edit in that file from Task 0

```bash
git add README.md docs/configuration.md docs/mcp.md docs/runbook.md docs/deploy.md \
  docs/sites.md docs/architecture.md docs/filters.md docs/orchestration.md
git commit -m "docs: describe job settings in Mongo"
```

---

## Task 15: Verify the whole flow in dev

**Files:** none, unless a check fails

- [ ] **Step 1: Run all checks**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

Run: `cd ui && bun run type-check && bunx vitest run && bun run build`
Expected: PASS

- [ ] **Step 2: Start dev and seed**

```bash
./scripts/run_dev.sh ui
```

```bash
./seed.sh job-settings
```

Expected: `[job-settings] inserted`. Run the seed again and expect `[job-settings] already there, unchanged`

- [ ] **Step 3: Set the dev values**

Open `http://localhost:8090/config`. Set the values read in Task 12 Step 3, such as keyword `data analyst`, with only `jobstreet` enabled and its limit at 30

- [ ] **Step 4: Check the page in the browser**

Use the built-in browser with `http://localhost:8090/config`. Check each of these and take a screenshot of the result

- The form shows version, time, and source, with no Proxy URL field
- Change `limit`, save, and see the version go up and the old version appear under Older versions
- Upwork shows `Use its own filter` ticked with empty fields. Save an unrelated change and check that `filter: {}` stays in Mongo
- LinkedIn shows `Jakarta, Indonesia` as one line, and `delay_seconds` 4 and 6
- Open the page in a second tab, save in one tab, then save in the other. The second save shows `These settings changed somewhere else. Reload and try again`
- Restore version 1. The values go back and the version goes up
- Clear a site limit and save. The site uses the global limit, and the `limit` key is gone from Mongo
- No console errors

Check the stored document with this command. The password stays inside the container

```bash
docker exec job-scraper-mongo sh -c 'mongosh -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --quiet job_scraper --eval "printjson(db.job_settings.findOne()); print(db.job_settings_history.countDocuments())"'
```

- [ ] **Step 5: Check the failure paths**

Each check here changes dev only

1. Delete the document with `db.job_settings.deleteOne({_id: "active"})`, start a run from the UI, and see the error that names `./seed.sh job-settings`. Run the seed again
2. Remove `SCRAPER_PROXY_URL` from `.env`, recreate `scraper-mcp`, start a run, and see the error that names the var. Put the line back and recreate
3. Run `docker stop job-scraper-mongo`, reload `/config`, and see that saving is off. Run `docker start job-scraper-mongo`

- [ ] **Step 6: Run a real scrape**

Run a scrape from the UI, then edit `keywords` and run again. The second run uses the new keyword with no restart

- [ ] **Step 7: Run the reviews**

Dispatch `code-reviewer`, then `security-reviewer`, one at a time, with model `sonnet` and effort `high`. Give them `git diff feat/scrape-save-run-option...HEAD`. Fix every CRITICAL and HIGH finding

---

## Task 16: Roll out to prod

**Stop here and ask the owner before each step.** These steps change the live service

- [ ] **Step 1: Set the GitHub variable**

Set `SCRAPER_PROXY_URL` to `socks5://localhost:1080` under repo variables. The deploy fails without it

- [ ] **Step 2: Seed prod Mongo**

Open the tunnel, then seed. Old code ignores this collection, so seeding before the deploy is safe. `seed.sh` reads the password from the local `.env`. If prod uses a different password, the owner sets `MONGO_ROOT_PASSWORD` in their shell first

```bash
./scripts/ssh-tunnel.sh mongo-up
```

```bash
MONGO_HOST=127.0.0.1 MONGO_PORT=27018 ./seed.sh job-settings
```

Expected: `[job-settings] inserted`

- [ ] **Step 3: Open and merge the PR**

Open the PR to `main` with the `pull-request` skill. The merge starts the deploy

- [ ] **Step 4: Check prod**

- `/health` on MCP reports `ok`
- Log in at the prod domain and open `/config`
- Save one small change, and restore it
- After the next cron run, the Discord post arrives and the run in Mongo has `ok: true`

- [ ] **Step 5: Roll back if needed**

Revert the merge commit and let the deploy run. The old image has its own baked `config.yaml`, and the new collections stay unused. Changes saved in Mongo do not carry back, so copy them into `config.yaml` first if they matter
