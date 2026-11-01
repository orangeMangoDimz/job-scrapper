# Scraper UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. If you use subagents, use Sonnet 5.5 with high effort and run one at a time. Steps use checkbox (`- [ ]`) syntax for tracking

**Goal:** Give `scraper/` its own web UI to run scrapes, see results, edit config, and watch live logs, with no change to `frontend/` or `backend/`

**Architecture:** A Vue app in `ui/` talks to a thin FastAPI service in `ui_server/`, which serves the Vue build from one image. The API calls `scraper-mcp` tools for scrapes and reads, writes config files itself in dev, tails a shared log volume, and saves each run under `output/ui-runs/<run_id>/`. Dev is local with no login. Prod is public through Caddy HTTPS with one password

**Tech Stack:** Python 3.13, FastAPI, uvicorn, pydantic-settings, `mcp` client, ruamel.yaml, argon2-cffi, itsdangerous, pytest. Vue 3, Pinia, vue-router, Tailwind 4, shadcn-vue components copied from `frontend/`, Vitest, Bun. Docker Compose, Caddy, GitHub Actions

---

## Settled decisions

| Topic | Decision |
| --- | --- |
| Location | `scraper/ui/` and `scraper/ui_server/`, nothing imported from `frontend/` or `backend/` |
| Controls | Run scrapes, see results, edit config, live logs |
| Scrape path | API calls MCP `scrape_jobs`, so `scraper-mcp` must be up |
| One run at a time | Second run gets 409. No stop button, because `scrape_jobs` has no cancel |
| Results | Each run saved to `output/ui-runs/<run_id>/`, last 50 kept. Mongo write stays, so jobs appear in Latest jobs |
| Dev config | Save to `config.yaml` with loader validation and backup, then rewrite `/tmp/config.dev.yaml` in place |
| Prod config | Read-only in UI. Changes go through git and deploy |
| Dev access | `127.0.0.1:8090`, no login |
| Prod access | Public through Caddy HTTPS, one password stored as hash, signed cookie, rate-limited login |
| Patterns | `{success, data, meta, error}` response, `routes/` plus `schema/` split from `backend/`. `domain/data/presentation` modules from `frontend/`, no code comments in `ui/` |

## Changes from the agreed design

Reading the code showed three things the design did not cover. This plan handles them as follows

1. **`MCP_HOST=127.0.0.1` would break the bot.** The bot calls `http://host.docker.internal:8080/mcp`, which resolves to the Docker gateway, not loopback. Task 19 binds prod `scraper-mcp` to the gateway IP through `MCP_BIND_HOST`, default `172.17.0.1`. Port 8080 stays closed to the public and the bot keeps working. The healthcheck URL changes to match
2. **Prod compose is invalid right now.** The uncommitted `networks` block in `docker-compose.yml` fails with `service scraper-mcp declares mutually exclusive network_mode and networks`. Task 19 fixes it with `networks: !reset []`
3. **`scrape_jobs` blocks the MCP server.** FastMCP runs sync tools on its event loop, so `list_sites` and `get_config` hang during a scrape. The API caches last good reads and marks them stale (Task 3)

Logs also use a named volume instead of `./logs`, because a bind mount would make `logs/scraper.log` unwritable for host runs. Same `PermissionError` as `output/`

## Before starting

- [ ] **Confirm where backend runs in prod.** Gateway binding works for containers on the same VPS. If backend runs on another machine, set `MCP_BIND_HOST=0.0.0.0` and add a firewall allow-list for the backend IP instead
- [ ] **Confirm on VPS:** `docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}'` prints `172.17.0.1`. If not, set `MCP_BIND_HOST` to the printed IP
- [ ] **Confirm on VPS:** `docker compose version --short` is 2.24 or newer, because Task 19 uses `!reset`
- [ ] **Have a domain pointing to the VPS, with ports 80 and 443 free**
- [ ] **Decide what to do with uncommitted changes.** `docker-compose.yml`, `requirements.txt`, and `scripts/run_dev.sh` already have your changes. Commit steps below that touch them will include those changes. Commit or stash them first
- [ ] **Commit steps run only if the user asked for commits.** Otherwise leave changes in the working tree and skip each commit step

## Known limits

- Replacing `keywords` through the UI drops commented-out keywords inside that list. Comments elsewhere in `config.yaml` are kept
- In dev, fields set in `config.dev.patch.yaml` are locked in the UI, because the patch would override them
- Logout clears the cookie only. A copied cookie stays valid until it expires after 12 hours
- When a session expires, pages show `You are not signed in.` until reload, which opens login
- `bot.schedule` is not editable. It is baked into the bot image
- Live logs show every line in `logs/scraper.log`, including cron runs
- During a scrape, `scraper-mcp` `/health` and backend calls wait until the scrape ends. This is existing behaviour

## File structure

```text
scraper/
├── Caddyfile                         prod HTTPS and security headers
├── ui_server/
│   ├── __init__.py
│   ├── __main__.py                   uvicorn entry
│   ├── app.py                        create_app, wiring, SPA static files
│   ├── dependencies.py               Services, get_services, require_session, reject_cross_site
│   ├── errors.py                     AppError types and handlers
│   ├── settings.py                   Settings
│   ├── requirements.txt
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── config.py
│   │   ├── logs.py
│   │   ├── runs.py
│   │   └── sites.py
│   ├── schema/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── config.py
│   │   ├── response.py
│   │   └── runs.py
│   └── services/
│       ├── __init__.py
│       ├── auth_service.py           password check, session cookie, login limiter
│       ├── config_store.py           comment-safe config writes, backup, dev merge
│       ├── log_tail.py               follow log file, redact secrets
│       ├── mcp_gateway.py            MCP calls and cached reads
│       ├── run_service.py            one-run lock, background task
│       └── run_store.py              run folders and retention
├── tests/
│   ├── test_ui_settings.py
│   ├── test_ui_errors.py
│   ├── test_ui_mcp_gateway.py
│   ├── test_ui_run_store.py
│   ├── test_ui_run_service.py
│   ├── test_ui_config_store.py
│   ├── test_ui_log_tail.py
│   ├── test_ui_auth.py
│   └── test_ui_routes.py
└── ui/
    ├── package.json, vite.config.ts, vitest.config.ts, index.html
    └── src/
        ├── main.ts, App.vue
        ├── router/index.ts
        ├── core/                     env, ApiError, httpClient
        ├── shared/                   copied styles, ui components, utils
        └── modules/
            ├── auth/
            ├── runs/
            └── config/
```

---

# Part A: API

## Task 1: Dependencies and settings

**Files:**
- Create: `ui_server/__init__.py`, `ui_server/routes/__init__.py`, `ui_server/schema/__init__.py`, `ui_server/services/__init__.py` (all empty)
- Create: `ui_server/requirements.txt`, `ui_server/settings.py`
- Modify: `pyproject.toml` (`known-first-party`)
- Test: `tests/test_ui_settings.py`

- [ ] **Step 1: Add dependencies**

`ui_server/requirements.txt`:

```text
# Kept apart from the root requirements.txt, which is baked into the scraper images
fastapi>=0.115,<1
uvicorn>=0.54,<1
pydantic-settings>=2.6,<3
mcp>=1.30,<2
httpx>=0.27,<1
pyyaml>=6.0
ruamel.yaml>=0.18,<1
argon2-cffi>=23.1
itsdangerous>=2.2,<3
```

Run: `uv pip install --python .venv/bin/python -r ui_server/requirements.txt`
Expected: packages installed with no resolver error

In `pyproject.toml`, change the isort line to:

```toml
known-first-party = ["scraper", "mcp_server", "ui_server"]
```

- [ ] **Step 2: Write the failing test**

`tests/test_ui_settings.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from ui_server.settings import Settings

STRONG_SECRET = "s" * 32


def test_dev_needs_no_secrets():
    settings = Settings(env="dev")

    assert settings.auth_enabled is False
    assert settings.config_read_only is False
    assert settings.cookie_secure is False


def test_prod_refuses_to_start_without_password_hash():
    with pytest.raises(ValidationError, match="UI_PASSWORD_HASH"):
        Settings(env="prod", session_secret=STRONG_SECRET)


def test_prod_refuses_short_session_secret():
    with pytest.raises(ValidationError, match="UI_SESSION_SECRET"):
        Settings(env="prod", password_hash="hash", session_secret="short")


def test_prod_turns_on_login_and_read_only_config():
    settings = Settings(env="prod", password_hash="hash", session_secret=STRONG_SECRET)

    assert settings.auth_enabled is True
    assert settings.config_read_only is True
    assert settings.cookie_secure is True
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ui_settings.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'ui_server.settings'`

- [ ] **Step 4: Write the implementation**

`ui_server/settings.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SESSION_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UI_", frozen=True)

    env: Literal["dev", "prod"] = "dev"
    host: str = "0.0.0.0"
    port: int = 8090
    mcp_url: str = "http://scraper-mcp:8080/mcp"
    runs_dir: Path = Path("output/ui-runs")
    log_path: Path = Path("logs/scraper.log")
    config_path: Path = Path("config.yaml")
    dev_patch_path: Path = Path("config.dev.patch.yaml")
    dev_merged_path: Path = Path("config.dev.yaml")
    backup_dir: Path = Path("config-backups")
    static_dir: Path = Path("ui/dist")
    password_hash: str = ""
    session_secret: str = ""
    keep_runs: int = 50

    @model_validator(mode="after")
    def require_prod_secrets(self) -> Self:
        if self.env != "prod":
            return self
        if not self.password_hash:
            raise ValueError("UI_PASSWORD_HASH is required in prod")
        if len(self.session_secret) < MIN_SESSION_SECRET_LENGTH:
            raise ValueError(
                f"UI_SESSION_SECRET must have at least {MIN_SESSION_SECRET_LENGTH} characters"
            )
        return self

    @property
    def auth_enabled(self) -> bool:
        return self.env == "prod"

    @property
    def config_read_only(self) -> bool:
        return self.env == "prod"

    @property
    def cookie_secure(self) -> bool:
        return self.env == "prod"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ui_settings.py`
Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add ui_server pyproject.toml tests/test_ui_settings.py
git commit -m "feat: add scraper UI settings"
```

## Task 2: Errors and response format

**Files:**
- Create: `ui_server/errors.py`, `ui_server/schema/response.py`
- Test: `tests/test_ui_errors.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ui_errors.py`:

```python
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from ui_server.errors import RunInProgressError, install_error_handlers
from ui_server.schema.response import ok


class Body(BaseModel):
    limit: int


def _client() -> TestClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/busy")
    def busy() -> None:
        raise RunInProgressError()

    @app.get("/crash")
    def crash() -> None:
        raise RuntimeError("secret detail")

    @app.post("/validate")
    def validate(body: Body) -> dict:
        return ok(body.limit)

    return TestClient(app, raise_server_exceptions=False)


def test_ok_wraps_data():
    assert ok({"a": 1}) == {"success": True, "data": {"a": 1}, "error": None}


def test_ok_adds_meta_when_given():
    assert ok([], meta={"total": 0})["meta"] == {"total": 0}


def test_app_error_uses_error_envelope():
    response = _client().get("/busy")

    assert response.status_code == 409
    assert response.json() == {
        "success": False,
        "data": None,
        "error": "A scrape is already running.",
    }


def test_validation_error_lists_fields():
    response = _client().post("/validate", json={"limit": "x"})

    assert response.status_code == 422
    assert list(response.json()["error"]) == ["limit"]


def test_unexpected_error_hides_detail():
    response = _client().get("/crash")

    assert response.status_code == 500
    assert "secret detail" not in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ui_errors.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'ui_server.errors'`

- [ ] **Step 3: Write the implementation**

`ui_server/schema/response.py`:

```python
from __future__ import annotations

from typing import Any


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"success": True, "data": data, "error": None}
    return body if meta is None else {**body, "meta": meta}


def failure(error: Any) -> dict[str, Any]:
    return {"success": False, "data": None, "error": error}
```

`ui_server/errors.py`:

```python
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ui_server.schema.response import failure

LOG = logging.getLogger("scraper-ui")
UNEXPECTED_MESSAGE = "Something went wrong. Try again."


class AppError(Exception):
    status_code = 400
    default_message = "The request could not be completed."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class NotSignedInError(AppError):
    status_code = 401
    default_message = "You are not signed in."


class InvalidPasswordError(AppError):
    status_code = 401
    default_message = "Wrong password."


class CrossSiteRequestError(AppError):
    status_code = 403
    default_message = "Cross-site requests are not allowed."


class ConfigReadOnlyError(AppError):
    status_code = 403
    default_message = "Config is read-only here. Change it through git and deploy."


class RunNotFoundError(AppError):
    status_code = 404
    default_message = "Run not found."


class RunInProgressError(AppError):
    status_code = 409
    default_message = "A scrape is already running."


class ConfigInvalidError(AppError):
    status_code = 422
    default_message = "That config is not valid."


class TooManyAttemptsError(AppError):
    status_code = 429
    default_message = "Too many tries. Try again in a few minutes."


class McpUnavailableError(AppError):
    status_code = 503
    default_message = "The scraper service could not be reached."


def _field_errors(exc: RequestValidationError) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for item in exc.errors():
        name = ".".join(str(part) for part in item["loc"][1:]) or "body"
        fields = {**fields, name: [*fields.get(name, []), item["msg"]]}
    return fields


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=failure(exc.message))

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content=failure(_field_errors(exc)))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        LOG.error("unhandled error on %s", request.url.path, exc_info=exc)
        return JSONResponse(status_code=500, content=failure(UNEXPECTED_MESSAGE))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ui_errors.py`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add ui_server/errors.py ui_server/schema/response.py tests/test_ui_errors.py
git commit -m "feat: add scraper UI errors and response format"
```

## Task 3: MCP gateway with cached reads

**Files:**
- Create: `ui_server/services/mcp_gateway.py`
- Test: `tests/test_ui_mcp_gateway.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ui_mcp_gateway.py`:

```python
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from ui_server.errors import McpUnavailableError
from ui_server.services.mcp_gateway import ScraperClient, read_structured


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses: list[dict[str, Any] | Exception] = []

    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        self.calls.append((tool, arguments))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_read_structured_returns_content():
    result = SimpleNamespace(isError=False, structuredContent={"ok": True})

    assert read_structured("list_sites", result) == {"ok": True}


def test_read_structured_rejects_tool_error():
    result = SimpleNamespace(isError=True, structuredContent=None)

    with pytest.raises(McpUnavailableError):
        read_structured("list_sites", result)


def test_read_structured_passes_tool_error_message():
    result = SimpleNamespace(isError=False, structuredContent={"error": "bad config"})

    with pytest.raises(McpUnavailableError, match="bad config"):
        read_structured("list_sites", result)


def test_read_returns_fresh_value():
    gateway = FakeGateway()
    gateway.responses = [{"sites": []}]

    read = asyncio.run(ScraperClient(gateway).read_sites())

    assert read.value == {"sites": []}
    assert read.is_stale is False


def test_read_falls_back_to_last_value_when_mcp_is_busy():
    gateway = FakeGateway()
    gateway.responses = [{"sites": ["a"]}, McpUnavailableError()]
    client = ScraperClient(gateway)

    async def read_twice():
        await client.read_sites()
        return await client.read_sites()

    read = asyncio.run(read_twice())

    assert read.value == {"sites": ["a"]}
    assert read.is_stale is True


def test_read_raises_when_nothing_is_cached():
    gateway = FakeGateway()
    gateway.responses = [McpUnavailableError()]

    with pytest.raises(McpUnavailableError):
        asyncio.run(ScraperClient(gateway).read_config())


def test_scrape_jobs_sends_sites_and_keywords():
    gateway = FakeGateway()
    gateway.responses = [{"ok": True}]

    asyncio.run(ScraperClient(gateway).scrape_jobs(("upwork",), ("django",)))

    assert gateway.calls == [("scrape_jobs", {"sites": ["upwork"], "keywords": ["django"]})]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ui_mcp_gateway.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'ui_server.services.mcp_gateway'`

- [ ] **Step 3: Write the implementation**

`ui_server/services/mcp_gateway.py`:

```python
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from ui_server.errors import McpUnavailableError

LOG = logging.getLogger("scraper-ui")
READ_TIMEOUT_SECONDS = 5.0
SCRAPE_TIMEOUT_SECONDS = 1800.0
CONNECT_TIMEOUT_SECONDS = 5.0


class McpGateway(Protocol):
    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CachedRead:
    value: dict[str, Any]
    is_stale: bool


def read_structured(tool: str, result: Any) -> dict[str, Any]:
    if result.isError or not isinstance(result.structuredContent, dict):
        LOG.warning("mcp tool %s returned no usable result", tool)
        raise McpUnavailableError()
    content = result.structuredContent
    if "error" in content:
        raise McpUnavailableError(str(content["error"]))
    return content


class HttpMcpGateway:
    def __init__(self, url: str) -> None:
        self._url = url

    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        try:
            async with asyncio.timeout(timeout_seconds):
                result = await self._open_session_and_call(tool, arguments, timeout_seconds)
        except Exception as exc:
            LOG.warning("mcp tool %s failed: %s", tool, exc)
            raise McpUnavailableError() from exc
        return read_structured(tool, result)

    async def _open_session_and_call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> Any:
        timeout = httpx.Timeout(timeout_seconds, connect=CONNECT_TIMEOUT_SECONDS)
        async with (
            httpx.AsyncClient(timeout=timeout) as http_client,
            streamable_http_client(self._url, http_client=http_client) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            return await session.call_tool(
                tool, arguments, read_timeout_seconds=timedelta(seconds=timeout_seconds)
            )


class ScraperClient:
    def __init__(self, gateway: McpGateway) -> None:
        self._gateway = gateway
        self._cache: dict[str, dict[str, Any]] = {}

    async def scrape_jobs(
        self, sites: tuple[str, ...], keywords: tuple[str, ...]
    ) -> dict[str, Any]:
        arguments = {"sites": list(sites), "keywords": list(keywords)}
        return await self._gateway.call("scrape_jobs", arguments, SCRAPE_TIMEOUT_SECONDS)

    async def read_sites(self) -> CachedRead:
        return await self._read("list_sites")

    async def read_config(self) -> CachedRead:
        return await self._read("get_config")

    async def _read(self, tool: str) -> CachedRead:
        try:
            value = await self._gateway.call(tool, {}, READ_TIMEOUT_SECONDS)
        except McpUnavailableError:
            if tool not in self._cache:
                raise
            return CachedRead(self._cache[tool], True)
        self._cache = {**self._cache, tool: value}
        return CachedRead(value, False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ui_mcp_gateway.py`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add ui_server/services/mcp_gateway.py tests/test_ui_mcp_gateway.py
git commit -m "feat: add MCP gateway for scraper UI"
```

## Task 4: Run store

**Files:**
- Create: `ui_server/services/run_store.py`
- Test: `tests/test_ui_run_store.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ui_run_store.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from ui_server.errors import RunNotFoundError
from ui_server.services.run_store import RunStatus, RunStore, flatten_result


def _store(tmp_path: Path, keep_runs: int = 50) -> RunStore:
    return RunStore(tmp_path / "ui-runs", keep_runs)


def _result(ok: bool, count: int) -> dict:
    jobs = [{"title": f"job {index}"} for index in range(count)]
    return {
        "ok": ok,
        "results": [{"keyword": "django", "sites": [{"site": "upwork", "jobs": jobs}]}],
        "errors": [] if ok else [{"keyword": "django", "site": "indeed", "reason": "timeout"}],
    }


def test_create_writes_running_record(tmp_path: Path):
    store = _store(tmp_path)

    record = store.create(("django",), ("upwork",))

    assert record.status is RunStatus.RUNNING
    assert store.get(record.id) == record


def test_finish_saves_result_and_counts(tmp_path: Path):
    store = _store(tmp_path)
    record = store.create(("django",), ("upwork",))

    finished = store.finish(record, _result(True, 2))

    assert finished.status is RunStatus.SUCCEEDED
    assert finished.job_count == 2
    assert store.read_result(record.id)["ok"] is True


def test_finish_with_some_jobs_and_errors_is_partial(tmp_path: Path):
    store = _store(tmp_path)

    finished = store.finish(store.create(("django",), ("upwork",)), _result(False, 1))

    assert finished.status is RunStatus.PARTIAL
    assert finished.error_count == 1


def test_finish_with_no_jobs_and_errors_is_failed(tmp_path: Path):
    store = _store(tmp_path)

    finished = store.finish(store.create(("django",), ("upwork",)), _result(False, 0))

    assert finished.status is RunStatus.FAILED


def test_fail_keeps_message(tmp_path: Path):
    store = _store(tmp_path)

    failed = store.fail(store.create(("django",), ("upwork",)), "MCP down")

    assert failed.status is RunStatus.FAILED
    assert store.get(failed.id).error == "MCP down"


def test_get_rejects_unsafe_id(tmp_path: Path):
    with pytest.raises(RunNotFoundError):
        _store(tmp_path).get("../../etc")


def test_get_rejects_unknown_id(tmp_path: Path):
    with pytest.raises(RunNotFoundError):
        _store(tmp_path).get("20261101T120000Z-abcdef")


def test_list_recent_returns_newest_first(tmp_path: Path):
    store = _store(tmp_path)
    first = store.create(("a",), ("upwork",))
    second = store.create(("b",), ("upwork",))

    ids = [record.id for record in store.list_recent()]

    assert ids == sorted([first.id, second.id], reverse=True)


def test_prune_keeps_newest_runs(tmp_path: Path):
    store = _store(tmp_path, keep_runs=1)
    old = store.finish(store.create(("a",), ("upwork",)), _result(True, 0))
    new = store.finish(store.create(("b",), ("upwork",)), _result(True, 0))
    newest = max(old.id, new.id)

    store.prune()

    assert [record.id for record in store.list_recent()] == [newest]


def test_mark_interrupted_closes_running_runs(tmp_path: Path):
    store = _store(tmp_path)
    record = store.create(("a",), ("upwork",))

    store.mark_interrupted()

    assert store.get(record.id).status is RunStatus.INTERRUPTED


def test_flatten_result_returns_jobs_and_failures():
    jobs, failures = flatten_result(_result(False, 1))

    assert jobs == [{"title": "job 0"}]
    assert failures == [{"keyword": "django", "site": "indeed", "reason": "timeout"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ui_run_store.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'ui_server.services.run_store'`

- [ ] **Step 3: Write the implementation**

`ui_server/services/run_store.py`:

```python
from __future__ import annotations

import json
import logging
import re
import secrets
import shutil
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from ui_server.errors import RunNotFoundError

LOG = logging.getLogger("scraper-ui")
RUN_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{6}$")
RECORD_FILE = "run.json"
RESULT_FILE = "result.json"
INTERRUPTED_MESSAGE = "The UI service restarted during this run."


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class RunRecord:
    id: str
    status: RunStatus
    keywords: tuple[str, ...]
    sites: tuple[str, ...]
    started_at: str
    finished_at: str | None = None
    job_count: int = 0
    error_count: int = 0
    error: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _new_run_id() -> str:
    return f"{_now():%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _to_record(payload: dict[str, Any]) -> RunRecord:
    return RunRecord(
        **{
            **payload,
            "status": RunStatus(payload["status"]),
            "keywords": tuple(payload["keywords"]),
            "sites": tuple(payload["sites"]),
        }
    )


def flatten_result(
    result: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    jobs = [
        job
        for group in result.get("results", [])
        for site in group.get("sites", [])
        for job in site.get("jobs", [])
    ]
    return jobs, list(result.get("errors", []))


def _status_for(result: dict[str, Any], job_count: int) -> RunStatus:
    if result.get("ok"):
        return RunStatus.SUCCEEDED
    return RunStatus.PARTIAL if job_count > 0 else RunStatus.FAILED


class RunStore:
    def __init__(self, root: Path, keep_runs: int) -> None:
        self._root = root
        self._keep_runs = keep_runs

    def create(self, keywords: tuple[str, ...], sites: tuple[str, ...]) -> RunRecord:
        record = RunRecord(
            id=_new_run_id(),
            status=RunStatus.RUNNING,
            keywords=keywords,
            sites=sites,
            started_at=_now().isoformat(),
        )
        self._run_dir(record.id).mkdir(parents=True)
        self._save(record)
        return record

    def finish(self, record: RunRecord, result: dict[str, Any]) -> RunRecord:
        jobs, failures = flatten_result(result)
        _write_json(self._run_dir(record.id) / RESULT_FILE, result)
        return self._save(
            replace(
                record,
                status=_status_for(result, len(jobs)),
                finished_at=_now().isoformat(),
                job_count=len(jobs),
                error_count=len(failures),
            )
        )

    def fail(self, record: RunRecord, message: str) -> RunRecord:
        return self._save(
            replace(
                record,
                status=RunStatus.FAILED,
                finished_at=_now().isoformat(),
                error=message,
            )
        )

    def get(self, run_id: str) -> RunRecord:
        path = self._record_path(run_id)
        if not path.exists():
            raise RunNotFoundError()
        return _to_record(json.loads(path.read_text(encoding="utf-8")))

    def read_result(self, run_id: str) -> dict[str, Any]:
        path = self._record_path(run_id).with_name(RESULT_FILE)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def list_recent(self) -> tuple[RunRecord, ...]:
        return tuple(self.get(run_id) for run_id in reversed(self._run_ids()))

    def mark_interrupted(self) -> None:
        for record in self.list_recent():
            if record.status is RunStatus.RUNNING:
                self._save(
                    replace(
                        record,
                        status=RunStatus.INTERRUPTED,
                        finished_at=_now().isoformat(),
                        error=INTERRUPTED_MESSAGE,
                    )
                )

    def prune(self) -> None:
        run_ids = self._run_ids()
        for run_id in run_ids[: max(len(run_ids) - self._keep_runs, 0)]:
            shutil.rmtree(self._run_dir(run_id))
            LOG.info("removed old run folder %s", run_id)

    def _run_ids(self) -> list[str]:
        if not self._root.exists():
            return []
        return sorted(
            path.name
            for path in self._root.iterdir()
            if RUN_ID_PATTERN.match(path.name) and (path / RECORD_FILE).exists()
        )

    def _run_dir(self, run_id: str) -> Path:
        return self._root / run_id

    def _record_path(self, run_id: str) -> Path:
        if not RUN_ID_PATTERN.match(run_id):
            raise RunNotFoundError()
        return self._run_dir(run_id) / RECORD_FILE

    def _save(self, record: RunRecord) -> RunRecord:
        _write_json(self._run_dir(record.id) / RECORD_FILE, asdict(record))
        return record
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ui_run_store.py`
Expected: `11 passed`

- [ ] **Step 5: Commit**

```bash
git add ui_server/services/run_store.py tests/test_ui_run_store.py
git commit -m "feat: add run folders for scraper UI"
```

## Task 5: Run service

**Files:**
- Create: `ui_server/services/run_service.py`
- Test: `tests/test_ui_run_service.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ui_run_service.py`:

```python
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ui_server.errors import McpUnavailableError, RunInProgressError
from ui_server.services.run_service import RunService
from ui_server.services.run_store import RunStatus, RunStore


class FakeScraper:
    def __init__(self, outcome: dict | Exception) -> None:
        self._outcome = outcome
        self.release = asyncio.Event()

    async def scrape_jobs(self, sites: tuple[str, ...], keywords: tuple[str, ...]) -> dict:
        await self.release.wait()
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _service(tmp_path: Path, scraper: FakeScraper) -> tuple[RunService, RunStore]:
    store = RunStore(tmp_path / "runs", keep_runs=50)
    return RunService(store, scraper), store


def test_run_finishes_and_saves_result(tmp_path: Path):
    async def scenario() -> RunStatus:
        scraper = FakeScraper({"ok": True, "results": [], "errors": []})
        service, store = _service(tmp_path, scraper)
        record = service.start(("django",), ("upwork",))
        scraper.release.set()
        await service.wait()
        return store.get(record.id).status

    assert asyncio.run(scenario()) is RunStatus.SUCCEEDED


def test_second_run_is_refused_while_first_is_active(tmp_path: Path):
    async def scenario() -> None:
        scraper = FakeScraper({"ok": True})
        service, _ = _service(tmp_path, scraper)
        service.start(("django",), ("upwork",))
        with pytest.raises(RunInProgressError):
            service.start(("flask",), ("upwork",))
        scraper.release.set()
        await service.wait()

    asyncio.run(scenario())


def test_new_run_is_allowed_after_first_finishes(tmp_path: Path):
    async def scenario() -> int:
        scraper = FakeScraper({"ok": True})
        service, store = _service(tmp_path, scraper)
        scraper.release.set()
        service.start(("django",), ("upwork",))
        await service.wait()
        service.start(("flask",), ("upwork",))
        await service.wait()
        return len(store.list_recent())

    assert asyncio.run(scenario()) == 2


def test_mcp_failure_marks_run_failed(tmp_path: Path):
    async def scenario() -> str | None:
        scraper = FakeScraper(McpUnavailableError("MCP down"))
        service, store = _service(tmp_path, scraper)
        record = service.start(("django",), ("upwork",))
        scraper.release.set()
        await service.wait()
        return store.get(record.id).error

    assert asyncio.run(scenario()) == "MCP down"


def test_unexpected_failure_hides_detail(tmp_path: Path):
    async def scenario() -> str | None:
        scraper = FakeScraper(RuntimeError("secret detail"))
        service, store = _service(tmp_path, scraper)
        record = service.start(("django",), ("upwork",))
        scraper.release.set()
        await service.wait()
        return store.get(record.id).error

    assert asyncio.run(scenario()) == "The scrape failed."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ui_run_service.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'ui_server.services.run_service'`

- [ ] **Step 3: Write the implementation**

`ui_server/services/run_service.py`:

```python
from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from ui_server.errors import McpUnavailableError, RunInProgressError
from ui_server.services.run_store import RunRecord, RunStore

LOG = logging.getLogger("scraper-ui")
RUN_FAILED_MESSAGE = "The scrape failed."


class Scraper(Protocol):
    async def scrape_jobs(
        self, sites: tuple[str, ...], keywords: tuple[str, ...]
    ) -> dict[str, Any]: ...


class RunService:
    def __init__(self, store: RunStore, scraper: Scraper) -> None:
        self._store = store
        self._scraper = scraper
        self._task: asyncio.Task[None] | None = None

    def start(self, keywords: tuple[str, ...], sites: tuple[str, ...]) -> RunRecord:
        if self._task is not None and not self._task.done():
            raise RunInProgressError()
        record = self._store.create(keywords, sites)
        self._task = asyncio.create_task(self._execute(record))
        return record

    async def wait(self) -> None:
        if self._task is not None:
            await self._task

    async def _execute(self, record: RunRecord) -> None:
        try:
            result = await self._scraper.scrape_jobs(record.sites, record.keywords)
            self._store.finish(record, result)
        except McpUnavailableError as exc:
            self._store.fail(record, exc.message)
        except Exception:
            LOG.exception("run %s failed", record.id)
            self._store.fail(record, RUN_FAILED_MESSAGE)
        self._store.prune()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ui_run_service.py`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add ui_server/services/run_service.py tests/test_ui_run_service.py
git commit -m "feat: add single-run service for scraper UI"
```

## Task 6: Config store

**Files:**
- Create: `ui_server/schema/config.py`, `ui_server/services/config_store.py`
- Test: `tests/test_ui_config_store.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ui_config_store.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ui_server.errors import ConfigInvalidError, ConfigReadOnlyError
from ui_server.schema.config import ConfigUpdateRequest
from ui_server.services.config_store import ConfigStore, deep_merge
from ui_server.settings import Settings

BASE = """# top comment
keywords:
  - devops
limit: 3
# proxy comment
proxy: "socks5://localhost:1080"
sites:
  jobstreet:
    enabled: true
    limit: 5
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs"
"""

PATCH = """proxy: ~
sites:
  jobstreet:
    limit: 30
"""


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        env="dev",
        config_path=tmp_path / "config.yaml",
        dev_patch_path=tmp_path / "patch.yaml",
        dev_merged_path=tmp_path / "merged.yaml",
        backup_dir=tmp_path / "backups",
    )


def _store(tmp_path: Path) -> ConfigStore:
    (tmp_path / "config.yaml").write_text(BASE)
    (tmp_path / "patch.yaml").write_text(PATCH)
    return ConfigStore(_settings(tmp_path))


def test_update_changes_value_and_keeps_comments(tmp_path: Path):
    store = _store(tmp_path)

    store.update(ConfigUpdateRequest(limit=9))

    text = (tmp_path / "config.yaml").read_text()
    assert yaml.safe_load(text)["limit"] == 9
    assert "# top comment" in text
    assert "# proxy comment" in text


def test_update_writes_in_place(tmp_path: Path):
    store = _store(tmp_path)
    inode_before = (tmp_path / "config.yaml").stat().st_ino

    store.update(ConfigUpdateRequest(limit=9))

    assert (tmp_path / "config.yaml").stat().st_ino == inode_before


def test_update_rewrites_merged_dev_config(tmp_path: Path):
    store = _store(tmp_path)

    store.update(ConfigUpdateRequest(keywords=["python"]))

    merged = yaml.safe_load((tmp_path / "merged.yaml").read_text())
    assert merged["keywords"] == ["python"]
    assert merged["proxy"] is None
    assert merged["sites"]["jobstreet"]["limit"] == 30


def test_update_makes_backup_first(tmp_path: Path):
    store = _store(tmp_path)

    store.update(ConfigUpdateRequest(limit=9))

    backups = list((tmp_path / "backups").iterdir())
    assert len(backups) == 1
    assert yaml.safe_load(backups[0].read_text())["limit"] == 3


def test_update_changes_site_fields(tmp_path: Path):
    store = _store(tmp_path)

    store.update(ConfigUpdateRequest(sites={"jobstreet": {"enabled": False}}))

    config = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert config["sites"]["jobstreet"]["enabled"] is False


def test_update_rejects_unknown_site(tmp_path: Path):
    with pytest.raises(ConfigInvalidError, match="ghost"):
        _store(tmp_path).update(ConfigUpdateRequest(sites={"ghost": {"enabled": True}}))


def test_update_rejects_field_locked_by_patch(tmp_path: Path):
    store = _store(tmp_path)

    with pytest.raises(ConfigInvalidError, match="proxy"):
        store.update(ConfigUpdateRequest(proxy_url="socks5://localhost:9999"))

    assert yaml.safe_load((tmp_path / "config.yaml").read_text())["limit"] == 3


def test_invalid_result_leaves_file_untouched(tmp_path: Path):
    store = _store(tmp_path)
    broken = BASE.replace("id.jobstreet.com", "evil.example.com")
    (tmp_path / "config.yaml").write_text(broken)

    with pytest.raises(ConfigInvalidError):
        store.update(ConfigUpdateRequest(limit=9))

    assert (tmp_path / "config.yaml").read_text() == broken
    assert not (tmp_path / "backups").exists()


def test_request_rejects_bad_proxy_url():
    with pytest.raises(ValidationError):
        ConfigUpdateRequest(proxy_url="not a proxy")


def test_request_accepts_empty_proxy_url():
    assert ConfigUpdateRequest(proxy_url=None).proxy_url is None


def test_update_is_refused_in_prod(tmp_path: Path):
    settings = Settings(env="prod", password_hash="hash", session_secret="s" * 32)

    with pytest.raises(ConfigReadOnlyError):
        ConfigStore(settings).update(ConfigUpdateRequest(limit=9))


def test_locked_paths_lists_patch_fields(tmp_path: Path):
    assert _store(tmp_path).locked_paths() == ("proxy", "sites.jobstreet.limit")


def test_locked_paths_is_empty_in_prod():
    settings = Settings(env="prod", password_hash="hash", session_secret="s" * 32)

    assert ConfigStore(settings).locked_paths() == ()


def test_deep_merge_replaces_lists_and_merges_maps():
    merged = deep_merge({"a": [1], "b": {"c": 1, "d": 2}}, {"a": [2], "b": {"c": 3}})

    assert merged == {"a": [2], "b": {"c": 3, "d": 2}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ui_config_store.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'ui_server.schema.config'`

- [ ] **Step 3: Write the implementation**

The loader accepts any proxy string, so the request schema checks the proxy URL itself

`ui_server/schema/config.py`:

```python
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_LIMIT = 200
MAX_AGE_HOURS = 720

Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
SiteName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]+$", max_length=40)]
ProxyUrl = Annotated[
    str, StringConstraints(pattern=r"^(socks5h?|https?)://\S+$", max_length=300)
]


class SiteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    limit: int | None = Field(default=None, ge=1, le=MAX_LIMIT)


class ConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: list[Keyword] | None = Field(default=None, min_length=1)
    limit: int | None = Field(default=None, ge=1, le=MAX_LIMIT)
    max_age_hours: int | None = Field(default=None, ge=1, le=MAX_AGE_HOURS)
    proxy_url: ProxyUrl | None = None
    sites: dict[SiteName, SiteUpdate] = Field(default_factory=dict)
```

`ui_server/services/config_store.py`:

```python
from __future__ import annotations

import io
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import yaml
from ruamel.yaml import YAML

from scraper.config_loader import ConfigError, load
from ui_server.errors import ConfigInvalidError, ConfigReadOnlyError
from ui_server.schema.config import ConfigUpdateRequest
from ui_server.settings import Settings

KEEP_BACKUPS = 20
YAML_LINE_WIDTH = 4096
TOP_LEVEL_FIELDS = {
    "keywords": "keywords",
    "limit": "limit",
    "max_age_hours": "max_age_hours",
    "proxy_url": "proxy",
}


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _flatten_paths(document: dict[str, Any], prefix: str = "") -> tuple[str, ...]:
    paths: list[str] = []
    for key, value in document.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            paths.extend(_flatten_paths(value, f"{path}."))
        else:
            paths.append(path)
    return tuple(paths)


def _changed_paths(changes: ConfigUpdateRequest) -> tuple[str, ...]:
    top_level = [
        path for field, path in TOP_LEVEL_FIELDS.items() if field in changes.model_fields_set
    ]
    per_site = [
        f"sites.{name}.{field}"
        for name, site in changes.sites.items()
        for field in sorted(site.model_fields_set)
    ]
    return (*top_level, *per_site)


def _new_yaml() -> YAML:
    round_trip = YAML()
    round_trip.preserve_quotes = True
    round_trip.width = YAML_LINE_WIDTH
    return round_trip


def _dump(document: Any) -> str:
    buffer = io.StringIO()
    _new_yaml().dump(document, buffer)
    return buffer.getvalue()


def _apply(document: Any, changes: ConfigUpdateRequest) -> None:
    for field, path in TOP_LEVEL_FIELDS.items():
        if field in changes.model_fields_set:
            document[path] = getattr(changes, field)
    sites = document.get("sites") or {}
    for name, site in changes.sites.items():
        if name not in sites:
            raise ConfigInvalidError(f"Unknown site: {name}")
        for field in site.model_fields_set:
            sites[name][field] = getattr(site, field)


def _validate(text: str) -> None:
    with tempfile.TemporaryDirectory() as folder:
        candidate = Path(folder) / "config.yaml"
        candidate.write_text(text, encoding="utf-8")
        try:
            load(candidate)
        except ConfigError as exc:
            raise ConfigInvalidError(str(exc)) from exc


class ConfigStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()

    def locked_paths(self) -> tuple[str, ...]:
        if self._settings.config_read_only:
            return ()
        patch = self._read_patch()
        return _flatten_paths(patch)

    def update(self, changes: ConfigUpdateRequest) -> None:
        if self._settings.config_read_only:
            raise ConfigReadOnlyError()
        with self._lock:
            self._reject_locked(changes)
            path = self._settings.config_path
            original = path.read_text(encoding="utf-8")
            document = _new_yaml().load(original)
            _apply(document, changes)
            text = _dump(document)
            _validate(text)
            self._backup(original)
            path.write_text(text, encoding="utf-8")
            self._write_merged(text)

    def _reject_locked(self, changes: ConfigUpdateRequest) -> None:
        locked = set(self.locked_paths())
        blocked = [path for path in _changed_paths(changes) if path in locked]
        if blocked:
            names = ", ".join(blocked)
            raise ConfigInvalidError(f"Set by config.dev.patch.yaml: {names}")

    def _read_patch(self) -> dict[str, Any]:
        path = self._settings.dev_patch_path
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def _backup(self, original: str) -> None:
        folder = self._settings.backup_dir
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"config.yaml.{time.time_ns()}").write_text(original, encoding="utf-8")
        for stale in sorted(folder.iterdir())[:-KEEP_BACKUPS]:
            stale.unlink()

    def _write_merged(self, text: str) -> None:
        merged = deep_merge(yaml.safe_load(text), self._read_patch())
        self._settings.dev_merged_path.write_text(
            yaml.safe_dump(merged, sort_keys=False), encoding="utf-8"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ui_config_store.py`
Expected: `14 passed`

- [ ] **Step 5: Commit**

```bash
git add ui_server/schema/config.py ui_server/services/config_store.py tests/test_ui_config_store.py
git commit -m "feat: add safe config writes for scraper UI"
```

## Task 7: Log tail

**Files:**
- Create: `ui_server/services/log_tail.py`
- Test: `tests/test_ui_log_tail.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ui_log_tail.py`:

```python
from __future__ import annotations

import asyncio
from pathlib import Path

from ui_server.services.log_tail import follow_lines, redact


async def _collect(path: Path, stop_after: int, on_poll=None) -> list[str]:
    polls = 0

    async def is_disconnected() -> bool:
        nonlocal polls
        polls += 1
        if on_poll is not None:
            on_poll(polls)
        return polls > stop_after

    lines: list[str] = []
    async for line in follow_lines(path, is_disconnected, poll_seconds=0):
        if line is not None:
            lines.append(line)
    return lines


def test_starts_with_last_lines(tmp_path: Path):
    path = tmp_path / "scraper.log"
    path.write_text("".join(f"line {index}\n" for index in range(100)))

    lines = asyncio.run(_collect(path, stop_after=2))

    assert len(lines) == 50
    assert lines[-1] == "line 99"


def test_follows_new_lines(tmp_path: Path):
    path = tmp_path / "scraper.log"
    path.write_text("first\n")

    def append(poll: int) -> None:
        if poll == 2:
            with path.open("a") as handle:
                handle.write("second\n")

    lines = asyncio.run(_collect(path, stop_after=4, on_poll=append))

    assert lines == ["first", "second"]


def test_keeps_partial_line_until_it_ends(tmp_path: Path):
    path = tmp_path / "scraper.log"
    path.write_text("")

    def append(poll: int) -> None:
        with path.open("a") as handle:
            if poll == 1:
                handle.write("hel")
            if poll == 3:
                handle.write("lo\n")

    lines = asyncio.run(_collect(path, stop_after=5, on_poll=append))

    assert lines == ["hello"]


def test_restarts_after_rotation(tmp_path: Path):
    path = tmp_path / "scraper.log"
    path.write_text("old line that is long\n")

    def rotate(poll: int) -> None:
        if poll == 2:
            path.write_text("new\n")

    lines = asyncio.run(_collect(path, stop_after=4, on_poll=rotate))

    assert lines == ["old line that is long", "new"]


def test_missing_file_waits_for_it(tmp_path: Path):
    path = tmp_path / "scraper.log"

    def create(poll: int) -> None:
        if poll == 2:
            path.write_text("hello\n")

    assert asyncio.run(_collect(path, stop_after=4, on_poll=create)) == ["hello"]


def test_redact_hides_url_credentials():
    line = "using proxy: socks5://user:secret@host:1080"

    assert redact(line) == "using proxy: socks5://***@host:1080"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ui_log_tail.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'ui_server.services.log_tail'`

- [ ] **Step 3: Write the implementation**

`ui_server/services/log_tail.py`:

```python
from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

INITIAL_LINES = 50
HEARTBEAT_SECONDS = 15.0
READ_CHUNK_BYTES = 65_536
URL_CREDENTIALS = re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+@")


def redact(line: str) -> str:
    return URL_CREDENTIALS.sub("***@", line)


def _read_last_lines(path: Path) -> tuple[list[str], int]:
    if not path.exists():
        return [], 0
    with path.open("rb") as handle:
        last_lines = deque(handle, maxlen=INITIAL_LINES)
        position = handle.tell()
    return [line.decode("utf-8", "replace").rstrip("\n") for line in last_lines], position


def _read_chunk(path: Path, position: int) -> tuple[bytes, int]:
    if not path.exists():
        return b"", 0
    size = path.stat().st_size
    start = 0 if size < position else position
    with path.open("rb") as handle:
        handle.seek(start)
        chunk = handle.read(READ_CHUNK_BYTES)
    return chunk, start + len(chunk)


async def follow_lines(
    path: Path,
    is_disconnected: Callable[[], Awaitable[bool]],
    poll_seconds: float = 0.5,
) -> AsyncIterator[str | None]:
    """Yield new log lines, or None when a heartbeat is due"""
    initial, position = _read_last_lines(path)
    for line in initial:
        yield line
    pending = b""
    last_sent = time.monotonic()
    while not await is_disconnected():
        chunk, position = _read_chunk(path, position)
        *lines, pending = (pending + chunk).split(b"\n")
        for line in lines:
            yield line.decode("utf-8", "replace")
            last_sent = time.monotonic()
        if time.monotonic() - last_sent >= HEARTBEAT_SECONDS:
            yield None
            last_sent = time.monotonic()
        await asyncio.sleep(poll_seconds)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ui_log_tail.py`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add ui_server/services/log_tail.py tests/test_ui_log_tail.py
git commit -m "feat: add log tail for scraper UI"
```

## Task 8: Auth service

**Files:**
- Create: `ui_server/services/auth_service.py`
- Test: `tests/test_ui_auth.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ui_auth.py`:

```python
from __future__ import annotations

import pytest
from argon2 import PasswordHasher

from ui_server.errors import InvalidPasswordError, TooManyAttemptsError
from ui_server.services.auth_service import MAX_FAILED_ATTEMPTS, AuthService, LoginLimiter
from ui_server.settings import Settings

PASSWORD = "correct horse battery"


def _service() -> AuthService:
    settings = Settings(
        env="prod",
        password_hash=PasswordHasher().hash(PASSWORD),
        session_secret="s" * 32,
    )
    return AuthService(settings)


def test_right_password_gives_valid_session():
    service = _service()

    token = service.login(PASSWORD, "1.1.1.1")

    assert service.is_signed_in(token) is True


def test_wrong_password_is_rejected():
    with pytest.raises(InvalidPasswordError):
        _service().login("wrong", "1.1.1.1")


def test_tampered_token_is_rejected():
    service = _service()

    assert service.is_signed_in(service.login(PASSWORD, "1.1.1.1") + "x") is False


def test_missing_token_is_rejected():
    assert _service().is_signed_in(None) is False


def test_too_many_failures_block_client():
    service = _service()
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(InvalidPasswordError):
            service.login("wrong", "1.1.1.1")

    with pytest.raises(TooManyAttemptsError):
        service.login(PASSWORD, "1.1.1.1")


def test_block_applies_to_one_client_only():
    service = _service()
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(InvalidPasswordError):
            service.login("wrong", "1.1.1.1")

    assert service.is_signed_in(service.login(PASSWORD, "2.2.2.2")) is True


def test_limiter_forgets_old_failures():
    now = [0.0]
    limiter = LoginLimiter(clock=lambda: now[0])
    for _ in range(MAX_FAILED_ATTEMPTS):
        limiter.record_failure("1.1.1.1")

    now[0] = 10_000.0

    limiter.check("1.1.1.1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ui_auth.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'ui_server.services.auth_service'`

- [ ] **Step 3: Write the implementation**

`ui_server/services/auth_service.py`:

```python
from __future__ import annotations

import time
from collections.abc import Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from itsdangerous import BadSignature, TimestampSigner

from ui_server.errors import InvalidPasswordError, TooManyAttemptsError
from ui_server.settings import Settings

SESSION_COOKIE = "scraper_ui_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
SESSION_SUBJECT = "owner"
SESSION_SALT = "scraper-ui-session"
MAX_FAILED_ATTEMPTS = 5
FAILURE_WINDOW_SECONDS = 15 * 60.0


class LoginLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._failures: dict[str, tuple[float, ...]] = {}

    def check(self, client: str) -> None:
        if len(self._recent(client)) >= MAX_FAILED_ATTEMPTS:
            raise TooManyAttemptsError()

    def record_failure(self, client: str) -> None:
        self._failures = {**self._failures, client: (*self._recent(client), self._clock())}

    def clear(self, client: str) -> None:
        self._failures = {key: value for key, value in self._failures.items() if key != client}

    def _recent(self, client: str) -> tuple[float, ...]:
        cutoff = self._clock() - FAILURE_WINDOW_SECONDS
        return tuple(moment for moment in self._failures.get(client, ()) if moment > cutoff)


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self._password_hash = settings.password_hash
        self._signer = TimestampSigner(settings.session_secret or "dev", salt=SESSION_SALT)
        self._hasher = PasswordHasher()
        self._limiter = LoginLimiter()

    def login(self, password: str, client: str) -> str:
        self._limiter.check(client)
        if not self._is_right_password(password):
            self._limiter.record_failure(client)
            raise InvalidPasswordError()
        self._limiter.clear(client)
        return self._signer.sign(SESSION_SUBJECT).decode()

    def is_signed_in(self, token: str | None) -> bool:
        if token is None:
            return False
        try:
            self._signer.unsign(token, max_age=SESSION_MAX_AGE_SECONDS)
        except BadSignature:
            return False
        return True

    def _is_right_password(self, password: str) -> bool:
        try:
            return self._hasher.verify(self._password_hash, password)
        except (VerificationError, InvalidHashError):
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ui_auth.py`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add ui_server/services/auth_service.py tests/test_ui_auth.py
git commit -m "feat: add password login for scraper UI"
```

## Task 9: Routes and app

**Files:**
- Create: `ui_server/dependencies.py`, `ui_server/app.py`, `ui_server/__main__.py`
- Create: `ui_server/schema/auth.py`, `ui_server/schema/runs.py`
- Create: `ui_server/routes/auth.py`, `ui_server/routes/config.py`, `ui_server/routes/logs.py`, `ui_server/routes/runs.py`, `ui_server/routes/sites.py`
- Test: `tests/test_ui_routes.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ui_routes.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from ui_server.app import create_app
from ui_server.errors import McpUnavailableError
from ui_server.settings import Settings

PASSWORD = "correct horse battery"
BASE_CONFIG = """keywords: [devops]
limit: 3
sites:
  upwork:
    enabled: true
    url_template: "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency"
"""
SITES = {
    "keywords": ["devops"],
    "limit": 3,
    "sites": [{"name": "upwork", "enabled": True, "url_template": "x", "sample_url": "x"}],
}
CONFIG = {
    "keywords": ["devops"],
    "limit": 3,
    "max_age_hours": 72,
    "proxy": None,
    "sites": {"upwork": {"enabled": True, "limit": 30, "url_template": "x"}},
}
SCRAPE_RESULT = {
    "ok": True,
    "results": [{"keyword": "devops", "sites": [{"site": "upwork", "jobs": [{"title": "A"}]}]}],
    "errors": [],
}


class FakeGateway:
    def __init__(self) -> None:
        self.is_down = False

    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        if self.is_down:
            raise McpUnavailableError()
        return {"list_sites": SITES, "get_config": CONFIG, "scrape_jobs": SCRAPE_RESULT}[tool]


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    (tmp_path / "config.yaml").write_text(BASE_CONFIG)
    (tmp_path / "patch.yaml").write_text("proxy: ~\n")
    values = {
        "env": "dev",
        "runs_dir": tmp_path / "runs",
        "log_path": tmp_path / "scraper.log",
        "config_path": tmp_path / "config.yaml",
        "dev_patch_path": tmp_path / "patch.yaml",
        "dev_merged_path": tmp_path / "merged.yaml",
        "backup_dir": tmp_path / "backups",
        "static_dir": tmp_path / "dist",
    }
    return Settings(**{**values, **overrides})


def _prod_settings(tmp_path: Path) -> Settings:
    return _settings(
        tmp_path,
        env="prod",
        password_hash=PasswordHasher().hash(PASSWORD),
        session_secret="s" * 32,
    )


@pytest.fixture
def gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
def client(tmp_path: Path, gateway: FakeGateway):
    with TestClient(create_app(_settings(tmp_path), gateway)) as test_client:
        yield test_client


@pytest.fixture
def prod_client(tmp_path: Path, gateway: FakeGateway):
    app = create_app(_prod_settings(tmp_path), gateway)
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


def _run(client: TestClient) -> dict:
    response = client.post("/api/runs", json={"keywords": ["devops"], "sites": ["upwork"]})
    assert response.status_code == 202
    return response.json()["data"]


def test_health_needs_no_login(prod_client: TestClient):
    assert prod_client.get("/health").json() == {"status": "ok"}


def test_session_reports_login_not_needed_in_dev(client: TestClient):
    assert client.get("/api/auth/session").json()["data"] == {
        "auth_required": False,
        "signed_in": True,
    }


def test_sites_returns_options(client: TestClient):
    data = client.get("/api/sites").json()["data"]

    assert data["keywords"] == ["devops"]
    assert data["sites"] == [{"name": "upwork", "enabled": True}]
    assert data["is_stale"] is False


def test_sites_returns_503_when_mcp_is_down(client: TestClient, gateway: FakeGateway):
    gateway.is_down = True

    response = client.get("/api/sites")

    assert response.status_code == 503
    assert response.json()["success"] is False


def test_start_run_then_read_result(client: TestClient):
    run = _run(client)

    detail = client.get(f"/api/runs/{run['id']}").json()["data"]

    assert detail["record"]["status"] == "succeeded"
    assert detail["record"]["job_count"] == 1
    assert detail["jobs"] == [{"title": "A"}]


def test_list_runs_includes_started_run(client: TestClient):
    run = _run(client)

    runs = client.get("/api/runs").json()["data"]

    assert [item["id"] for item in runs] == [run["id"]]


def test_start_run_rejects_unknown_site(client: TestClient):
    response = client.post("/api/runs", json={"keywords": ["devops"], "sites": ["ghost"]})

    assert response.status_code == 422


def test_start_run_needs_keywords(client: TestClient):
    response = client.post("/api/runs", json={"keywords": [], "sites": ["upwork"]})

    assert response.status_code == 422


def test_unknown_run_returns_404(client: TestClient):
    assert client.get("/api/runs/nope").status_code == 404


def test_config_read_shows_locked_fields(client: TestClient):
    data = client.get("/api/config").json()["data"]

    assert data["read_only"] is False
    assert data["locked"] == ["proxy"]
    assert data["values"]["sites"] == [{"name": "upwork", "enabled": True, "limit": 30}]


def test_config_update_writes_file(client: TestClient, tmp_path: Path):
    response = client.put("/api/config", json={"limit": 9})

    assert response.status_code == 200
    assert "limit: 9" in (tmp_path / "config.yaml").read_text()


def test_cross_site_write_is_refused(client: TestClient):
    response = client.put(
        "/api/config", json={"limit": 9}, headers={"sec-fetch-site": "cross-site"}
    )

    assert response.status_code == 403


def test_prod_requires_login(prod_client: TestClient):
    assert prod_client.get("/api/runs").status_code == 401
    assert prod_client.get("/api/logs/stream").status_code == 401


def test_prod_login_opens_api_and_sets_safe_cookie(prod_client: TestClient):
    response = prod_client.post("/api/auth/login", json={"password": PASSWORD})

    cookie = response.headers["set-cookie"].lower()
    assert response.status_code == 200
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=strict" in cookie
    assert prod_client.get("/api/runs").status_code == 200


def test_prod_wrong_password_returns_401(prod_client: TestClient):
    response = prod_client.post("/api/auth/login", json={"password": "wrong"})

    assert response.status_code == 401


def test_prod_logout_clears_session(prod_client: TestClient):
    prod_client.post("/api/auth/login", json={"password": PASSWORD})

    prod_client.post("/api/auth/logout")

    assert prod_client.get("/api/runs").status_code == 401


def test_prod_config_is_read_only(prod_client: TestClient):
    prod_client.post("/api/auth/login", json={"password": PASSWORD})

    assert prod_client.get("/api/config").json()["data"]["read_only"] is True
    assert prod_client.put("/api/config", json={"limit": 9}).status_code == 403


def test_spa_paths_fall_back_to_index(tmp_path: Path, gateway: FakeGateway):
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("<html>app</html>")
    with TestClient(create_app(_settings(tmp_path), gateway)) as test_client:
        assert "app" in test_client.get("/config").text
        assert test_client.get("/api/missing").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ui_routes.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'ui_server.app'`

- [ ] **Step 3: Write schemas and dependencies**

`ui_server/schema/auth.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

MAX_PASSWORD_LENGTH = 200


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
```

`ui_server/schema/runs.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ui_server.schema.config import Keyword, SiteName

MAX_KEYWORDS = 20
MAX_SITES = 20


class StartRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: list[Keyword] = Field(min_length=1, max_length=MAX_KEYWORDS)
    sites: list[SiteName] = Field(min_length=1, max_length=MAX_SITES)
```

`ui_server/dependencies.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request

from ui_server.errors import CrossSiteRequestError, NotSignedInError
from ui_server.services.auth_service import SESSION_COOKIE, AuthService
from ui_server.services.config_store import ConfigStore
from ui_server.services.mcp_gateway import ScraperClient
from ui_server.services.run_service import RunService
from ui_server.services.run_store import RunStore
from ui_server.settings import Settings

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
ALLOWED_FETCH_SITES = frozenset({"same-origin", "none"})


@dataclass(frozen=True)
class Services:
    settings: Settings
    scraper: ScraperClient
    run_store: RunStore
    run_service: RunService
    config_store: ConfigStore
    auth: AuthService


def get_services(request: Request) -> Services:
    return request.app.state.services


def require_session(request: Request, services: Services = Depends(get_services)) -> None:
    if not services.settings.auth_enabled:
        return
    if not services.auth.is_signed_in(request.cookies.get(SESSION_COOKIE)):
        raise NotSignedInError()


def reject_cross_site(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site is not None and fetch_site not in ALLOWED_FETCH_SITES:
        raise CrossSiteRequestError()
```

- [ ] **Step 4: Write routes**

`ui_server/routes/auth.py`:

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from ui_server.dependencies import Services, get_services
from ui_server.schema.auth import LoginRequest
from ui_server.schema.response import ok
from ui_server.services.auth_service import SESSION_COOKIE, SESSION_MAX_AGE_SECONDS

UNKNOWN_CLIENT = "unknown"

router = APIRouter(prefix="/api/auth")


@router.get("/session")
def read_session(request: Request, services: Services = Depends(get_services)) -> dict[str, Any]:
    required = services.settings.auth_enabled
    signed_in = not required or services.auth.is_signed_in(request.cookies.get(SESSION_COOKIE))
    return ok({"auth_required": required, "signed_in": signed_in})


@router.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    client = request.client.host if request.client else UNKNOWN_CLIENT
    token = services.auth.login(body.password, client)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=services.settings.cookie_secure,
        samesite="strict",
    )
    return ok(None)


@router.post("/logout")
def logout(response: Response, services: Services = Depends(get_services)) -> dict[str, Any]:
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        secure=services.settings.cookie_secure,
        samesite="strict",
    )
    return ok(None)
```

`ui_server/routes/sites.py`:

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ui_server.dependencies import Services, get_services, require_session
from ui_server.schema.response import ok

router = APIRouter(prefix="/api/sites", dependencies=[Depends(require_session)])


@router.get("")
async def read_sites(services: Services = Depends(get_services)) -> dict[str, Any]:
    read = await services.scraper.read_sites()
    return ok(
        {
            "keywords": read.value.get("keywords", []),
            "sites": [
                {"name": site["name"], "enabled": site["enabled"]}
                for site in read.value.get("sites", [])
            ],
            "is_stale": read.is_stale,
        }
    )
```

`ui_server/routes/runs.py`:

```python
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, status

from ui_server.dependencies import Services, get_services, require_session
from ui_server.errors import ConfigInvalidError
from ui_server.schema.response import ok
from ui_server.schema.runs import StartRunRequest
from ui_server.services.run_store import flatten_result

router = APIRouter(prefix="/api/runs", dependencies=[Depends(require_session)])


@router.get("")
def list_runs(services: Services = Depends(get_services)) -> dict[str, Any]:
    return ok([asdict(record) for record in services.run_store.list_recent()])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    body: StartRunRequest, services: Services = Depends(get_services)
) -> dict[str, Any]:
    read = await services.scraper.read_sites()
    known = {site["name"] for site in read.value.get("sites", [])}
    unknown = sorted(set(body.sites) - known)
    if unknown:
        raise ConfigInvalidError(f"Unknown site: {', '.join(unknown)}")
    record = services.run_service.start(tuple(body.keywords), tuple(body.sites))
    return ok(asdict(record))


@router.get("/{run_id}")
def read_run(run_id: str, services: Services = Depends(get_services)) -> dict[str, Any]:
    record = services.run_store.get(run_id)
    jobs, failures = flatten_result(services.run_store.read_result(run_id))
    return ok({"record": asdict(record), "jobs": jobs, "failures": failures})
```

`ui_server/routes/config.py`:

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ui_server.dependencies import Services, get_services, require_session
from ui_server.schema.config import ConfigUpdateRequest
from ui_server.schema.response import ok

router = APIRouter(prefix="/api/config", dependencies=[Depends(require_session)])


def _to_values(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "keywords": config.get("keywords", []),
        "limit": config.get("limit"),
        "max_age_hours": config.get("max_age_hours"),
        "proxy_url": config.get("proxy"),
        "sites": [
            {"name": name, "enabled": site.get("enabled", True), "limit": site.get("limit")}
            for name, site in (config.get("sites") or {}).items()
        ],
    }


@router.get("")
async def read_config(services: Services = Depends(get_services)) -> dict[str, Any]:
    read = await services.scraper.read_config()
    return ok(
        {
            "values": _to_values(read.value),
            "read_only": services.settings.config_read_only,
            "locked": list(services.config_store.locked_paths()),
            "is_stale": read.is_stale,
        }
    )


@router.put("")
def update_config(
    body: ConfigUpdateRequest, services: Services = Depends(get_services)
) -> dict[str, Any]:
    services.config_store.update(body)
    return ok(None)
```

`ui_server/routes/logs.py`:

```python
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ui_server.dependencies import Services, get_services, require_session
from ui_server.services.log_tail import follow_lines, redact

HEARTBEAT_EVENT = ": ping\n\n"

router = APIRouter(prefix="/api/logs", dependencies=[Depends(require_session)])


@router.get("/stream")
async def stream_logs(
    request: Request, services: Services = Depends(get_services)
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        async for line in follow_lines(services.settings.log_path, request.is_disconnected):
            yield HEARTBEAT_EVENT if line is None else f"data: {redact(line)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 5: Write app and entry point**

`ui_server/app.py`:

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.types import Scope

from ui_server.dependencies import Services, reject_cross_site
from ui_server.errors import install_error_handlers
from ui_server.routes import auth, config, logs, runs, sites
from ui_server.services.auth_service import AuthService
from ui_server.services.config_store import ConfigStore
from ui_server.services.mcp_gateway import HttpMcpGateway, McpGateway, ScraperClient
from ui_server.services.run_service import RunService
from ui_server.services.run_store import RunStore
from ui_server.settings import Settings

NOT_FOUND_STATUS = 404
API_PREFIX = "api"
INDEX_FILE = "index.html"


class SpaStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Any:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != NOT_FOUND_STATUS or path.startswith(API_PREFIX):
                raise
            return await super().get_response(INDEX_FILE, scope)


def _build_services(settings: Settings, gateway: McpGateway) -> Services:
    scraper = ScraperClient(gateway)
    run_store = RunStore(settings.runs_dir, settings.keep_runs)
    return Services(
        settings=settings,
        scraper=scraper,
        run_store=run_store,
        run_service=RunService(run_store, scraper),
        config_store=ConfigStore(settings),
        auth=AuthService(settings),
    )


def create_app(settings: Settings | None = None, gateway: McpGateway | None = None) -> FastAPI:
    resolved = settings or Settings()
    services = _build_services(resolved, gateway or HttpMcpGateway(resolved.mcp_url))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        services.run_store.mark_interrupted()
        yield

    app = FastAPI(
        title="Scraper UI",
        lifespan=lifespan,
        dependencies=[Depends(reject_cross_site)],
        docs_url=None if resolved.env == "prod" else "/docs",
        redoc_url=None,
        openapi_url=None if resolved.env == "prod" else "/openapi.json",
    )
    app.state.services = services
    install_error_handlers(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for module in (auth, sites, runs, config, logs):
        app.include_router(module.router)
    if resolved.static_dir.exists():
        app.mount("/", SpaStaticFiles(directory=resolved.static_dir, html=True), name="ui")
    return app
```

`ui_server/__main__.py`:

```python
from __future__ import annotations

import logging

import uvicorn

from ui_server.app import create_app
from ui_server.settings import Settings


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, proxy_headers=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ui_routes.py`
Expected: `18 passed`

Note: `test_start_run_then_read_result` reads the run right after start. If it sees `running`, the `TestClient` event loop has not finished the task. Fix by polling in `_run` until the status leaves `running`, with a 2 second limit. Do not add a sleep to the app

- [ ] **Step 7: Run all scraper tests and linters**

Run: `.venv/bin/pytest`
Expected: all tests pass

Run: `.venv/bin/ruff check ui_server tests/test_ui_*.py`
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git add ui_server tests/test_ui_routes.py
git commit -m "feat: add scraper UI API routes"
```

---

# Part B: Vue app

Follow `frontend/AGENTS.md`: no code comments, `domain/data/presentation` layers, one use case per action

## Task 10: Project setup and copied files

**Files:**
- Create: `ui/package.json`, `ui/vite.config.ts`, `ui/vitest.config.ts`, `ui/index.html`, `ui/.gitignore`
- Copy from `frontend/`: tsconfig files, `env.d.ts`, `.prettierrc.json`, styles, `ui` components, `cn`, `loadStatus`, `ApiError`, HTTP interceptors

- [ ] **Step 1: Copy shared files**

Run from `scraper/`:

```bash
mkdir -p ui/src/shared/components/ui ui/src/shared/styles ui/src/shared/utils ui/src/core/errors ui/src/core/http/interceptors ui/src/core/config ui/src/router
```

```bash
cp ../frontend/tsconfig.json ../frontend/tsconfig.app.json ../frontend/tsconfig.node.json ../frontend/tsconfig.vitest.json ../frontend/env.d.ts ../frontend/.prettierrc.json ui/
```

```bash
cp ../frontend/src/shared/styles/*.css ui/src/shared/styles/
```

```bash
cp -r ../frontend/src/shared/components/ui/{badge,button,checkbox,input,label,separator,skeleton,sonner} ui/src/shared/components/ui/
```

```bash
find ui/src/shared/components/ui -type d -name __tests__ -exec rm -rf {} +
```

```bash
cp ../frontend/src/shared/utils/cn.ts ../frontend/src/shared/utils/loadStatus.ts ui/src/shared/utils/
```

```bash
cp ../frontend/src/core/errors/ApiError.ts ui/src/core/errors/
```

```bash
cp ../frontend/src/core/http/interceptors/envelopeInterceptor.ts ../frontend/src/core/http/interceptors/errorInterceptor.ts ui/src/core/http/interceptors/
```

- [ ] **Step 2: Add project files**

`ui/package.json`:

```json
{
  "name": "scraper-ui",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite --port 5174",
    "build": "vue-tsc --build && vite build",
    "test:unit": "vitest",
    "type-check": "vue-tsc --build",
    "format": "prettier --write src/"
  },
  "dependencies": {
    "@lucide/vue": "^1.55.0",
    "@tailwindcss/vite": "^4.3.3",
    "@vueuse/core": "^15.0.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "pinia": "^4.0.3",
    "reka-ui": "^2.11.0",
    "shadcn-vue": "^2.8.2",
    "tailwind-merge": "^3.7.0",
    "tailwindcss": "^4.3.3",
    "tw-animate-css": "^1.4.0",
    "vue": "rc",
    "vue-router": "^5.3.1",
    "vue-sonner": "^2.0.9"
  },
  "devDependencies": {
    "@tsconfig/node24": "^24.0.5",
    "@types/jsdom": "^30.0.0",
    "@types/node": "^24.13.4",
    "@vitejs/plugin-vue": "^6.0.8",
    "@vue/test-utils": "^2.5.0",
    "@vue/tsconfig": "^0.9.1",
    "jsdom": "^30.0.1",
    "prettier": "3.9.6",
    "typescript": "~6.0.0",
    "vite": "^8.2.2",
    "vitest": "^4.1.11",
    "vue-tsc": "^3.3.11"
  },
  "engines": {
    "node": "^22.18.0 || >=24.12.0"
  },
  "overrides": {
    "vue": "rc",
    "@vue/compiler-core": "rc",
    "@vue/compiler-dom": "rc",
    "@vue/compiler-sfc": "rc",
    "@vue/compiler-ssr": "rc",
    "@vue/compiler-vapor": "rc",
    "@vue/reactivity": "rc",
    "@vue/runtime-core": "rc",
    "@vue/runtime-dom": "rc",
    "@vue/runtime-vapor": "rc",
    "@vue/server-renderer": "rc",
    "@vue/shared": "rc",
    "@vue/compat": "rc"
  }
}
```

`ui/vite.config.ts`:

```ts
import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'

const DEFAULT_PROXY_TARGET = 'http://127.0.0.1:8090'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: process.env.API_PROXY_TARGET ?? DEFAULT_PROXY_TARGET,
        changeOrigin: true,
      },
    },
  },
})
```

`ui/vitest.config.ts`:

```ts
import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults } from 'vitest/config'
import viteConfig from './vite.config.ts'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      exclude: [...configDefaults.exclude],
      root: fileURLToPath(new URL('./', import.meta.url)),
    },
  }),
)
```

`ui/index.html`:

```html
<!doctype html>
<html lang="en" data-theme="light">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap"
    />
    <title>Scraper</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

`ui/.gitignore`:

```text
node_modules/
dist/
*.tsbuildinfo
```

- [ ] **Step 3: Install packages**

Run: `cd ui && bun install`
Expected: `bun.lock` created, no error

- [ ] **Step 4: Commit**

```bash
git add ui
git commit -m "feat: scaffold scraper UI with frontend styles"
```

## Task 11: Core HTTP and app shell

**Files:**
- Create: `ui/src/core/config/env.ts`, `ui/src/core/http/httpClient.ts`
- Create: `ui/src/main.ts`, `ui/src/App.vue`, `ui/src/router/index.ts`
- Test: `ui/src/core/http/__tests__/httpClient.spec.ts`

- [ ] **Step 1: Write the failing test**

`ui/src/core/http/__tests__/httpClient.spec.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/core/errors/ApiError'
import { HttpClient } from '@/core/http/httpClient'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status })
}

describe('HttpClient', () => {
  it('returns envelope data on success', async () => {
    const fetchFn = vi.fn().mockResolvedValue(jsonResponse(200, { success: true, data: [1] }))
    const client = new HttpClient('/api', fetchFn)

    await expect(client.get('/runs')).resolves.toEqual([1])
    expect(fetchFn.mock.calls[0]?.[0]).toBe('/api/runs')
  })

  it('sends JSON bodies', async () => {
    const fetchFn = vi.fn().mockResolvedValue(jsonResponse(202, { success: true, data: null }))
    const client = new HttpClient('/api', fetchFn)

    await client.post('/runs', { keywords: ['a'] })

    const init = fetchFn.mock.calls[0]?.[1] as RequestInit
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"keywords":["a"]}')
  })

  it('raises ApiError with the server message', async () => {
    const fetchFn = vi
      .fn()
      .mockResolvedValue(jsonResponse(409, { success: false, error: 'Already running' }))
    const client = new HttpClient('/api', fetchFn)

    const error = await client.post('/runs', {}).catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(409)
    expect((error as ApiError).message).toBe('Already running')
  })

  it('turns network failures into ApiError', async () => {
    const fetchFn = vi.fn().mockRejectedValue(new TypeError('failed'))
    const client = new HttpClient('/api', fetchFn)

    const error = await client.get('/runs').catch((caught: unknown) => caught)

    expect((error as ApiError).status).toBe(0)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && bun run test:unit --run src/core/http`
Expected: FAIL, cannot resolve `@/core/http/httpClient`

- [ ] **Step 3: Write the implementation**

`ui/src/core/config/env.ts`:

```ts
export const env = {
  apiBaseUrl: '/api',
}
```

`ui/src/core/http/httpClient.ts`:

```ts
import { env } from '@/core/config/env'
import { unwrapEnvelope } from '@/core/http/interceptors/envelopeInterceptor'
import { toApiError, toNetworkError } from '@/core/http/interceptors/errorInterceptor'

const DEFAULT_TIMEOUT_MS = 15_000
const JSON_CONTENT_TYPE = 'application/json'

type HttpMethod = 'GET' | 'POST' | 'PUT'

export class HttpClient {
  private readonly baseUrl: string
  private readonly fetchFn: typeof fetch

  constructor(baseUrl: string, fetchFn: typeof fetch = (...args) => fetch(...args)) {
    this.baseUrl = baseUrl
    this.fetchFn = fetchFn
  }

  get<T>(path: string): Promise<T> {
    return this.request<T>('GET', path)
  }

  post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>('POST', path, body)
  }

  put<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>('PUT', path, body)
  }

  private async request<T>(method: HttpMethod, path: string, body?: unknown): Promise<T> {
    const response = await this.send(method, path, body)
    if (!response.ok) {
      throw await toApiError(response)
    }
    return unwrapEnvelope<T>(response)
  }

  private async send(method: HttpMethod, path: string, body?: unknown): Promise<Response> {
    try {
      return await this.fetchFn(`${this.baseUrl}${path}`, {
        method,
        credentials: 'same-origin',
        headers: body === undefined ? {} : { 'Content-Type': JSON_CONTENT_TYPE },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
      })
    } catch (error) {
      throw toNetworkError(error)
    }
  }
}

export const httpClient = new HttpClient(env.apiBaseUrl)
```

`ui/src/router/index.ts`:

```ts
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/runs' },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/modules/auth/presentation/pages/LoginPage.vue'),
      meta: { isPublic: true },
    },
    {
      path: '/runs',
      name: 'runs',
      component: () => import('@/modules/runs/presentation/pages/RunsPage.vue'),
    },
    {
      path: '/config',
      name: 'config',
      component: () => import('@/modules/config/presentation/pages/ConfigPage.vue'),
    },
  ],
})

export default router
```

`ui/src/App.vue`:

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/modules/auth/presentation/stores/useAuthStore'
import { Button } from '@/shared/components/ui/button'
import { Toaster } from '@/shared/components/ui/sonner'

const NAV_ITEMS = [
  { to: '/runs', label: 'Runs' },
  { to: '/config', label: 'Config' },
]

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const showsNav = computed(() => route.meta.isPublic !== true)

async function signOut(): Promise<void> {
  await auth.logout()
  await router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-surface text-ink">
    <header v-if="showsNav" class="border-b border-line">
      <div class="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3">
        <span class="text-subheading">Scraper</span>
        <nav aria-label="Main navigation" class="flex gap-4">
          <RouterLink
            v-for="item in NAV_ITEMS"
            :key="item.to"
            :to="item.to"
            class="text-body-sm text-ink-muted"
            active-class="text-ink"
          >
            {{ item.label }}
          </RouterLink>
        </nav>
        <Button v-if="auth.isAuthRequired" class="ml-auto" variant="ink" @click="signOut">
          Sign out
        </Button>
      </div>
    </header>
    <main class="mx-auto max-w-5xl px-4 py-6">
      <RouterView />
    </main>
    <Toaster />
  </div>
</template>
```

`ui/src/main.ts`:

```ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'

import '@/shared/styles/main.css'

import { provideAuthUseCases } from '@/modules/auth/presentation/stores/authUseCases'
import { useAuthStore } from '@/modules/auth/presentation/stores/useAuthStore'
import { createAuthUseCases } from '@/modules/auth/routes'
import { provideConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'
import { createConfigUseCases } from '@/modules/config/routes'
import { provideRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'
import { createRunUseCases } from '@/modules/runs/routes'

import App from './App.vue'
import router from './router'

provideAuthUseCases(createAuthUseCases())
provideRunUseCases(createRunUseCases())
provideConfigUseCases(createConfigUseCases())

const app = createApp(App)
app.use(createPinia())

const auth = useAuthStore()
router.beforeEach(async (to) => {
  await auth.ensureSession().catch(() => undefined)
  if (to.meta.isPublic === true || auth.isSignedIn) {
    return true
  }
  return { name: 'login' }
})

app.use(router)
app.mount('#app')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && bun run test:unit --run src/core/http`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add ui/src/core ui/src/router ui/src/App.vue ui/src/main.ts
git commit -m "feat: add HTTP client and shell for scraper UI"
```

## Task 12: Auth module

**Files:**
- Create: `ui/src/modules/auth/domain/entities/Session.ts`
- Create: `ui/src/modules/auth/domain/repositories/AuthRepository.ts`
- Create: `ui/src/modules/auth/domain/usecases/{GetSessionUseCase,LoginUseCase,LogoutUseCase}.ts`
- Create: `ui/src/modules/auth/data/repositories/AuthRepositoryImpl.ts`
- Create: `ui/src/modules/auth/presentation/stores/{authUseCases,useAuthStore}.ts`
- Create: `ui/src/modules/auth/presentation/pages/LoginPage.vue`
- Create: `ui/src/modules/auth/routes.ts`
- Test: `ui/src/modules/auth/presentation/stores/__tests__/useAuthStore.spec.ts`

- [ ] **Step 1: Write the failing test**

`ui/src/modules/auth/presentation/stores/__tests__/useAuthStore.spec.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { provideAuthUseCases } from '@/modules/auth/presentation/stores/authUseCases'
import { useAuthStore } from '@/modules/auth/presentation/stores/useAuthStore'

const getSession = { execute: vi.fn() }
const login = { execute: vi.fn() }
const logout = { execute: vi.fn() }

describe('useAuthStore', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    provideAuthUseCases({ getSession, login, logout })
  })

  it('reads the session once', async () => {
    getSession.execute.mockResolvedValue({ isAuthRequired: false, isSignedIn: true })
    const store = useAuthStore()

    await store.ensureSession()
    await store.ensureSession()

    expect(store.isSignedIn).toBe(true)
    expect(getSession.execute).toHaveBeenCalledTimes(1)
  })

  it('signs in after a right password', async () => {
    login.execute.mockResolvedValue(undefined)
    const store = useAuthStore()

    await expect(store.login('secret')).resolves.toBe(true)

    expect(store.isSignedIn).toBe(true)
  })

  it('keeps the error after a wrong password', async () => {
    login.execute.mockRejectedValue(new Error('Wrong password.'))
    const store = useAuthStore()

    await expect(store.login('wrong')).resolves.toBe(false)

    expect(store.errorMessage).toBe('Wrong password.')
    expect(store.isSignedIn).toBe(false)
  })

  it('signs out', async () => {
    login.execute.mockResolvedValue(undefined)
    logout.execute.mockResolvedValue(undefined)
    const store = useAuthStore()
    await store.login('secret')

    await store.logout()

    expect(store.isSignedIn).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && bun run test:unit --run src/modules/auth`
Expected: FAIL, cannot resolve `@/modules/auth/presentation/stores/authUseCases`

- [ ] **Step 3: Write the implementation**

`ui/src/modules/auth/domain/entities/Session.ts`:

```ts
export interface Session {
  isAuthRequired: boolean
  isSignedIn: boolean
}
```

`ui/src/modules/auth/domain/repositories/AuthRepository.ts`:

```ts
import type { Session } from '@/modules/auth/domain/entities/Session'

export interface AuthRepository {
  getSession(): Promise<Session>
  login(password: string): Promise<void>
  logout(): Promise<void>
}
```

`ui/src/modules/auth/domain/usecases/GetSessionUseCase.ts`:

```ts
import type { Session } from '@/modules/auth/domain/entities/Session'
import type { AuthRepository } from '@/modules/auth/domain/repositories/AuthRepository'

export class GetSessionUseCase {
  private readonly repository: AuthRepository

  constructor(repository: AuthRepository) {
    this.repository = repository
  }

  execute(): Promise<Session> {
    return this.repository.getSession()
  }
}
```

`ui/src/modules/auth/domain/usecases/LoginUseCase.ts`:

```ts
import type { AuthRepository } from '@/modules/auth/domain/repositories/AuthRepository'

export class LoginUseCase {
  private readonly repository: AuthRepository

  constructor(repository: AuthRepository) {
    this.repository = repository
  }

  execute(password: string): Promise<void> {
    return this.repository.login(password)
  }
}
```

`ui/src/modules/auth/domain/usecases/LogoutUseCase.ts`:

```ts
import type { AuthRepository } from '@/modules/auth/domain/repositories/AuthRepository'

export class LogoutUseCase {
  private readonly repository: AuthRepository

  constructor(repository: AuthRepository) {
    this.repository = repository
  }

  execute(): Promise<void> {
    return this.repository.logout()
  }
}
```

`ui/src/modules/auth/data/repositories/AuthRepositoryImpl.ts`:

```ts
import type { HttpClient } from '@/core/http/httpClient'
import type { Session } from '@/modules/auth/domain/entities/Session'
import type { AuthRepository } from '@/modules/auth/domain/repositories/AuthRepository'

interface SessionModel {
  auth_required: boolean
  signed_in: boolean
}

export class AuthRepositoryImpl implements AuthRepository {
  private readonly client: HttpClient

  constructor(client: HttpClient) {
    this.client = client
  }

  async getSession(): Promise<Session> {
    const model = await this.client.get<SessionModel>('/auth/session')
    return { isAuthRequired: model.auth_required, isSignedIn: model.signed_in }
  }

  login(password: string): Promise<void> {
    return this.client.post<void>('/auth/login', { password })
  }

  logout(): Promise<void> {
    return this.client.post<void>('/auth/logout')
  }
}
```

`ui/src/modules/auth/presentation/stores/authUseCases.ts`:

```ts
import type { GetSessionUseCase } from '@/modules/auth/domain/usecases/GetSessionUseCase'
import type { LoginUseCase } from '@/modules/auth/domain/usecases/LoginUseCase'
import type { LogoutUseCase } from '@/modules/auth/domain/usecases/LogoutUseCase'

export interface AuthUseCases {
  getSession: Pick<GetSessionUseCase, 'execute'>
  login: Pick<LoginUseCase, 'execute'>
  logout: Pick<LogoutUseCase, 'execute'>
}

let useCases: AuthUseCases | null = null

export function provideAuthUseCases(next: AuthUseCases): void {
  useCases = next
}

export function requireAuthUseCases(): AuthUseCases {
  if (useCases === null) {
    throw new Error('Auth use cases are not provided')
  }
  return useCases
}
```

`ui/src/modules/auth/presentation/stores/useAuthStore.ts`:

```ts
import { ref } from 'vue'
import { defineStore } from 'pinia'
import { requireAuthUseCases } from '@/modules/auth/presentation/stores/authUseCases'

const FALLBACK_ERROR_MESSAGE = 'Could not sign in. Try again.'

function toMessage(error: unknown): string {
  return error instanceof Error ? error.message : FALLBACK_ERROR_MESSAGE
}

export const useAuthStore = defineStore('auth', () => {
  const isAuthRequired = ref(false)
  const isSignedIn = ref(false)
  const isSessionKnown = ref(false)
  const errorMessage = ref<string | null>(null)

  async function ensureSession(): Promise<void> {
    if (isSessionKnown.value) {
      return
    }
    const session = await requireAuthUseCases().getSession.execute()
    isAuthRequired.value = session.isAuthRequired
    isSignedIn.value = session.isSignedIn
    isSessionKnown.value = true
  }

  async function login(password: string): Promise<boolean> {
    errorMessage.value = null
    try {
      await requireAuthUseCases().login.execute(password)
      isSignedIn.value = true
      return true
    } catch (error) {
      errorMessage.value = toMessage(error)
      return false
    }
  }

  async function logout(): Promise<void> {
    await requireAuthUseCases().logout.execute()
    isSignedIn.value = false
  }

  return { isAuthRequired, isSignedIn, errorMessage, ensureSession, login, logout }
})
```

`ui/src/modules/auth/presentation/pages/LoginPage.vue`:

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/modules/auth/presentation/stores/useAuthStore'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

const auth = useAuthStore()
const router = useRouter()
const password = ref('')
const isSubmitting = ref(false)

async function submit(): Promise<void> {
  isSubmitting.value = true
  const isDone = await auth.login(password.value)
  isSubmitting.value = false
  if (isDone) {
    await router.push('/runs')
  }
}
</script>

<template>
  <section class="mx-auto mt-24 max-w-sm">
    <h1 class="text-title">Scraper</h1>
    <form class="mt-6 flex flex-col gap-4" @submit.prevent="submit">
      <div class="flex flex-col gap-2">
        <Label for="password">Password</Label>
        <Input id="password" v-model="password" type="password" autocomplete="current-password" />
      </div>
      <p v-if="auth.errorMessage" role="alert" class="text-body-sm">{{ auth.errorMessage }}</p>
      <Button type="submit" :disabled="password === '' || isSubmitting">Sign in</Button>
    </form>
  </section>
</template>
```

`ui/src/modules/auth/routes.ts`:

```ts
import { httpClient } from '@/core/http/httpClient'
import { AuthRepositoryImpl } from '@/modules/auth/data/repositories/AuthRepositoryImpl'
import { GetSessionUseCase } from '@/modules/auth/domain/usecases/GetSessionUseCase'
import { LoginUseCase } from '@/modules/auth/domain/usecases/LoginUseCase'
import { LogoutUseCase } from '@/modules/auth/domain/usecases/LogoutUseCase'
import type { AuthUseCases } from '@/modules/auth/presentation/stores/authUseCases'

export function createAuthUseCases(): AuthUseCases {
  const repository = new AuthRepositoryImpl(httpClient)
  return {
    getSession: new GetSessionUseCase(repository),
    login: new LoginUseCase(repository),
    logout: new LogoutUseCase(repository),
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && bun run test:unit --run src/modules/auth`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules/auth
git commit -m "feat: add login to scraper UI"
```

## Task 13: Runs module

**Files:**
- Create: `ui/src/modules/runs/domain/entities/Run.ts`
- Create: `ui/src/modules/runs/domain/repositories/RunRepository.ts`
- Create: `ui/src/modules/runs/domain/usecases/{GetRunOptionsUseCase,GetRunUseCase,ListRunsUseCase,StartRunUseCase}.ts`
- Create: `ui/src/modules/runs/data/models/RunModel.ts`
- Create: `ui/src/modules/runs/data/repositories/RunRepositoryImpl.ts`
- Create: `ui/src/modules/runs/presentation/stores/{runUseCases,useRunStore}.ts`
- Create: `ui/src/modules/runs/presentation/composables/useLiveLog.ts`
- Create: `ui/src/modules/runs/presentation/components/{RunForm,RunHistory,RunResults,LiveLogPanel}.vue`
- Create: `ui/src/modules/runs/presentation/pages/RunsPage.vue`
- Create: `ui/src/modules/runs/routes.ts`
- Test: `ui/src/modules/runs/presentation/stores/__tests__/useRunStore.spec.ts`, `ui/src/modules/runs/data/models/__tests__/RunModel.spec.ts`

- [ ] **Step 1: Write the failing tests**

`ui/src/modules/runs/data/models/__tests__/RunModel.spec.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { toRunDetail, type RunDetailModel } from '@/modules/runs/data/models/RunModel'

const MODEL: RunDetailModel = {
  record: {
    id: 'run-1',
    status: 'partial',
    keywords: ['django'],
    sites: ['upwork'],
    started_at: '2026-11-01T10:00:00+00:00',
    finished_at: '2026-11-01T10:01:00+00:00',
    job_count: 1,
    error_count: 1,
    error: null,
  },
  jobs: [
    {
      site: 'upwork',
      matched_keyword: 'django',
      title: 'Engineer',
      company: 'Upwork Client',
      location: 'Remote',
      url: 'https://www.upwork.com/jobs/1',
      posted_at: '2026-11-01T09:00:00+00:00',
    },
  ],
  failures: [{ keyword: 'django', site: 'indeed', reason: 'timeout' }],
}

describe('toRunDetail', () => {
  it('maps API fields', () => {
    const detail = toRunDetail(MODEL)

    expect(detail.record.jobCount).toBe(1)
    expect(detail.record.startedAt).toBe('2026-11-01T10:00:00+00:00')
    expect(detail.jobs[0]?.matchedKeyword).toBe('django')
    expect(detail.failures[0]?.reason).toBe('timeout')
  })

  it('fills missing job fields with null', () => {
    const detail = toRunDetail({ ...MODEL, jobs: [{ title: 'Only title' }] })

    expect(detail.jobs[0]?.company).toBeNull()
  })
})
```

`ui/src/modules/runs/presentation/stores/__tests__/useRunStore.spec.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { RunDetail, RunRecord } from '@/modules/runs/domain/entities/Run'
import { provideRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'
import { POLL_INTERVAL_MS, useRunStore } from '@/modules/runs/presentation/stores/useRunStore'

const getOptions = { execute: vi.fn() }
const getRun = { execute: vi.fn() }
const listRuns = { execute: vi.fn() }
const startRun = { execute: vi.fn() }

function record(status: RunRecord['status']): RunRecord {
  return {
    id: 'run-1',
    status,
    keywords: ['django'],
    sites: ['upwork'],
    startedAt: '2026-11-01T10:00:00+00:00',
    finishedAt: null,
    jobCount: 0,
    errorCount: 0,
    error: null,
  }
}

function detail(status: RunRecord['status']): RunDetail {
  return { record: record(status), jobs: [], failures: [] }
}

describe('useRunStore', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useFakeTimers()
    setActivePinia(createPinia())
    provideRunUseCases({ getOptions, getRun, listRuns, startRun })
    listRuns.execute.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads options and history', async () => {
    getOptions.execute.mockResolvedValue({
      keywords: ['django'],
      sites: [{ name: 'upwork', isEnabled: true }],
      isStale: false,
    })
    const store = useRunStore()

    await store.load()

    expect(store.status).toBe('ready')
    expect(store.options?.keywords).toEqual(['django'])
  })

  it('shows an error when options fail', async () => {
    getOptions.execute.mockRejectedValue(new Error('Scraper down'))
    const store = useRunStore()

    await store.load()

    expect(store.status).toBe('error')
    expect(store.errorMessage).toBe('Scraper down')
  })

  it('polls a started run until it ends', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    getRun.execute
      .mockResolvedValueOnce(detail('running'))
      .mockResolvedValueOnce(detail('succeeded'))
    const store = useRunStore()

    await store.start(['django'], ['upwork'])
    expect(store.isRunning).toBe(true)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.isRunning).toBe(true)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.isRunning).toBe(false)
    expect(store.selected?.record.status).toBe('succeeded')
    expect(getRun.execute).toHaveBeenCalledTimes(2)
  })

  it('keeps the message when a run cannot start', async () => {
    startRun.execute.mockRejectedValue(new Error('A scrape is already running.'))
    const store = useRunStore()

    await store.start(['django'], ['upwork'])

    expect(store.startError).toBe('A scrape is already running.')
    expect(store.isRunning).toBe(false)
  })

  it('stops polling when asked', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    getRun.execute.mockResolvedValue(detail('running'))
    const store = useRunStore()
    await store.start(['django'], ['upwork'])

    store.stopPolling()
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

    expect(getRun.execute).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ui && bun run test:unit --run src/modules/runs`
Expected: FAIL, cannot resolve `@/modules/runs/data/models/RunModel`

- [ ] **Step 3: Write domain layer**

`ui/src/modules/runs/domain/entities/Run.ts`:

```ts
export type RunStatus = 'running' | 'succeeded' | 'partial' | 'failed' | 'interrupted'

export interface RunRecord {
  id: string
  status: RunStatus
  keywords: string[]
  sites: string[]
  startedAt: string
  finishedAt: string | null
  jobCount: number
  errorCount: number
  error: string | null
}

export interface RunJob {
  site: string | null
  matchedKeyword: string | null
  title: string | null
  company: string | null
  location: string | null
  url: string | null
  postedAt: string | null
}

export interface RunFailure {
  keyword: string
  site: string
  reason: string
}

export interface RunDetail {
  record: RunRecord
  jobs: RunJob[]
  failures: RunFailure[]
}

export interface SiteOption {
  name: string
  isEnabled: boolean
}

export interface RunOptions {
  keywords: string[]
  sites: SiteOption[]
  isStale: boolean
}
```

`ui/src/modules/runs/domain/repositories/RunRepository.ts`:

```ts
import type { RunDetail, RunOptions, RunRecord } from '@/modules/runs/domain/entities/Run'

export interface RunRepository {
  getOptions(): Promise<RunOptions>
  listRuns(): Promise<RunRecord[]>
  getRun(id: string): Promise<RunDetail>
  startRun(keywords: string[], sites: string[]): Promise<RunRecord>
}
```

`ui/src/modules/runs/domain/usecases/GetRunOptionsUseCase.ts`:

```ts
import type { RunOptions } from '@/modules/runs/domain/entities/Run'
import type { RunRepository } from '@/modules/runs/domain/repositories/RunRepository'

export class GetRunOptionsUseCase {
  private readonly repository: RunRepository

  constructor(repository: RunRepository) {
    this.repository = repository
  }

  execute(): Promise<RunOptions> {
    return this.repository.getOptions()
  }
}
```

`ui/src/modules/runs/domain/usecases/ListRunsUseCase.ts`:

```ts
import type { RunRecord } from '@/modules/runs/domain/entities/Run'
import type { RunRepository } from '@/modules/runs/domain/repositories/RunRepository'

export class ListRunsUseCase {
  private readonly repository: RunRepository

  constructor(repository: RunRepository) {
    this.repository = repository
  }

  execute(): Promise<RunRecord[]> {
    return this.repository.listRuns()
  }
}
```

`ui/src/modules/runs/domain/usecases/GetRunUseCase.ts`:

```ts
import type { RunDetail } from '@/modules/runs/domain/entities/Run'
import type { RunRepository } from '@/modules/runs/domain/repositories/RunRepository'

export class GetRunUseCase {
  private readonly repository: RunRepository

  constructor(repository: RunRepository) {
    this.repository = repository
  }

  execute(id: string): Promise<RunDetail> {
    return this.repository.getRun(id)
  }
}
```

`ui/src/modules/runs/domain/usecases/StartRunUseCase.ts`:

```ts
import type { RunRecord } from '@/modules/runs/domain/entities/Run'
import type { RunRepository } from '@/modules/runs/domain/repositories/RunRepository'

export class StartRunUseCase {
  private readonly repository: RunRepository

  constructor(repository: RunRepository) {
    this.repository = repository
  }

  execute(keywords: string[], sites: string[]): Promise<RunRecord> {
    return this.repository.startRun(keywords, sites)
  }
}
```

- [ ] **Step 4: Write data layer**

`ui/src/modules/runs/data/models/RunModel.ts`:

```ts
import type {
  RunDetail,
  RunJob,
  RunOptions,
  RunRecord,
  RunStatus,
} from '@/modules/runs/domain/entities/Run'

export interface RunRecordModel {
  id: string
  status: RunStatus
  keywords: string[]
  sites: string[]
  started_at: string
  finished_at: string | null
  job_count: number
  error_count: number
  error: string | null
}

export interface RunJobModel {
  site?: string | null
  matched_keyword?: string | null
  title?: string | null
  company?: string | null
  location?: string | null
  url?: string | null
  posted_at?: string | null
}

export interface RunDetailModel {
  record: RunRecordModel
  jobs: RunJobModel[]
  failures: RunDetail['failures']
}

export interface RunOptionsModel {
  keywords: string[]
  sites: { name: string; enabled: boolean }[]
  is_stale: boolean
}

export function toRunRecord(model: RunRecordModel): RunRecord {
  return {
    id: model.id,
    status: model.status,
    keywords: model.keywords,
    sites: model.sites,
    startedAt: model.started_at,
    finishedAt: model.finished_at,
    jobCount: model.job_count,
    errorCount: model.error_count,
    error: model.error,
  }
}

function toRunJob(model: RunJobModel): RunJob {
  return {
    site: model.site ?? null,
    matchedKeyword: model.matched_keyword ?? null,
    title: model.title ?? null,
    company: model.company ?? null,
    location: model.location ?? null,
    url: model.url ?? null,
    postedAt: model.posted_at ?? null,
  }
}

export function toRunDetail(model: RunDetailModel): RunDetail {
  return {
    record: toRunRecord(model.record),
    jobs: model.jobs.map(toRunJob),
    failures: model.failures,
  }
}

export function toRunOptions(model: RunOptionsModel): RunOptions {
  return {
    keywords: model.keywords,
    sites: model.sites.map((site) => ({ name: site.name, isEnabled: site.enabled })),
    isStale: model.is_stale,
  }
}
```

`ui/src/modules/runs/data/repositories/RunRepositoryImpl.ts`:

```ts
import type { HttpClient } from '@/core/http/httpClient'
import {
  toRunDetail,
  toRunOptions,
  toRunRecord,
  type RunDetailModel,
  type RunOptionsModel,
  type RunRecordModel,
} from '@/modules/runs/data/models/RunModel'
import type { RunDetail, RunOptions, RunRecord } from '@/modules/runs/domain/entities/Run'
import type { RunRepository } from '@/modules/runs/domain/repositories/RunRepository'

export class RunRepositoryImpl implements RunRepository {
  private readonly client: HttpClient

  constructor(client: HttpClient) {
    this.client = client
  }

  async getOptions(): Promise<RunOptions> {
    return toRunOptions(await this.client.get<RunOptionsModel>('/sites'))
  }

  async listRuns(): Promise<RunRecord[]> {
    const models = await this.client.get<RunRecordModel[]>('/runs')
    return models.map(toRunRecord)
  }

  async getRun(id: string): Promise<RunDetail> {
    return toRunDetail(await this.client.get<RunDetailModel>(`/runs/${encodeURIComponent(id)}`))
  }

  async startRun(keywords: string[], sites: string[]): Promise<RunRecord> {
    return toRunRecord(await this.client.post<RunRecordModel>('/runs', { keywords, sites }))
  }
}
```

`ui/src/modules/runs/routes.ts`:

```ts
import { httpClient } from '@/core/http/httpClient'
import { RunRepositoryImpl } from '@/modules/runs/data/repositories/RunRepositoryImpl'
import { GetRunOptionsUseCase } from '@/modules/runs/domain/usecases/GetRunOptionsUseCase'
import { GetRunUseCase } from '@/modules/runs/domain/usecases/GetRunUseCase'
import { ListRunsUseCase } from '@/modules/runs/domain/usecases/ListRunsUseCase'
import { StartRunUseCase } from '@/modules/runs/domain/usecases/StartRunUseCase'
import type { RunUseCases } from '@/modules/runs/presentation/stores/runUseCases'

export function createRunUseCases(): RunUseCases {
  const repository = new RunRepositoryImpl(httpClient)
  return {
    getOptions: new GetRunOptionsUseCase(repository),
    getRun: new GetRunUseCase(repository),
    listRuns: new ListRunsUseCase(repository),
    startRun: new StartRunUseCase(repository),
  }
}
```

- [ ] **Step 5: Write stores**

`ui/src/modules/runs/presentation/stores/runUseCases.ts`:

```ts
import type { GetRunOptionsUseCase } from '@/modules/runs/domain/usecases/GetRunOptionsUseCase'
import type { GetRunUseCase } from '@/modules/runs/domain/usecases/GetRunUseCase'
import type { ListRunsUseCase } from '@/modules/runs/domain/usecases/ListRunsUseCase'
import type { StartRunUseCase } from '@/modules/runs/domain/usecases/StartRunUseCase'

export interface RunUseCases {
  getOptions: Pick<GetRunOptionsUseCase, 'execute'>
  getRun: Pick<GetRunUseCase, 'execute'>
  listRuns: Pick<ListRunsUseCase, 'execute'>
  startRun: Pick<StartRunUseCase, 'execute'>
}

let useCases: RunUseCases | null = null

export function provideRunUseCases(next: RunUseCases): void {
  useCases = next
}

export function requireRunUseCases(): RunUseCases {
  if (useCases === null) {
    throw new Error('Run use cases are not provided')
  }
  return useCases
}
```

`ui/src/modules/runs/presentation/stores/useRunStore.ts`:

```ts
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { RunDetail, RunOptions, RunRecord } from '@/modules/runs/domain/entities/Run'
import { requireRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'
import type { LoadStatus } from '@/shared/utils/loadStatus'

export const POLL_INTERVAL_MS = 2000
const FALLBACK_ERROR_MESSAGE = 'Something went wrong. Try again.'

function toMessage(error: unknown): string {
  return error instanceof Error ? error.message : FALLBACK_ERROR_MESSAGE
}

export const useRunStore = defineStore('runs', () => {
  const status = ref<LoadStatus>('idle')
  const options = ref<RunOptions | null>(null)
  const runs = ref<RunRecord[]>([])
  const selected = ref<RunDetail | null>(null)
  const activeRunId = ref<string | null>(null)
  const errorMessage = ref<string | null>(null)
  const startError = ref<string | null>(null)
  let pollTimer: ReturnType<typeof setTimeout> | null = null

  const isRunning = computed(() => activeRunId.value !== null)

  async function refreshHistory(): Promise<void> {
    runs.value = await requireRunUseCases().listRuns.execute()
  }

  function followRun(id: string): void {
    activeRunId.value = id
    pollTimer = setTimeout(() => void poll(id), POLL_INTERVAL_MS)
  }

  async function load(): Promise<void> {
    status.value = 'loading'
    errorMessage.value = null
    try {
      const useCases = requireRunUseCases()
      const [nextOptions, nextRuns] = await Promise.all([
        useCases.getOptions.execute(),
        useCases.listRuns.execute(),
      ])
      options.value = nextOptions
      runs.value = nextRuns
      status.value = 'ready'
      const active = nextRuns.find((run) => run.status === 'running')
      if (active !== undefined && activeRunId.value === null) {
        followRun(active.id)
      }
    } catch (error) {
      errorMessage.value = toMessage(error)
      status.value = 'error'
    }
  }

  async function poll(id: string): Promise<void> {
    try {
      const detail = await requireRunUseCases().getRun.execute(id)
      if (detail.record.status === 'running') {
        followRun(id)
        return
      }
      selected.value = detail
      activeRunId.value = null
      await refreshHistory()
    } catch (error) {
      startError.value = toMessage(error)
      activeRunId.value = null
    }
  }

  async function start(keywords: string[], sites: string[]): Promise<void> {
    startError.value = null
    try {
      const record = await requireRunUseCases().startRun.execute(keywords, sites)
      await refreshHistory()
      followRun(record.id)
    } catch (error) {
      startError.value = toMessage(error)
    }
  }

  async function select(id: string): Promise<void> {
    try {
      selected.value = await requireRunUseCases().getRun.execute(id)
    } catch (error) {
      startError.value = toMessage(error)
    }
  }

  function stopPolling(): void {
    if (pollTimer !== null) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
    activeRunId.value = null
  }

  return {
    status,
    options,
    runs,
    selected,
    errorMessage,
    startError,
    isRunning,
    load,
    start,
    select,
    stopPolling,
  }
})
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd ui && bun run test:unit --run src/modules/runs`
Expected: `7 passed`

- [ ] **Step 7: Write the page and components**

`ui/src/modules/runs/presentation/composables/useLiveLog.ts`:

```ts
import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

const LOG_STREAM_PATH = '/api/logs/stream'
const MAX_LINES = 500

export function useLiveLog(): { lines: Ref<string[]>; isConnected: Ref<boolean> } {
  const lines = ref<string[]>([])
  const isConnected = ref(false)
  let source: EventSource | null = null

  onMounted(() => {
    source = new EventSource(LOG_STREAM_PATH)
    source.onopen = () => {
      isConnected.value = true
    }
    source.onerror = () => {
      isConnected.value = false
    }
    source.onmessage = (event: MessageEvent<string>) => {
      lines.value = [...lines.value, event.data].slice(-MAX_LINES)
    }
  })

  onBeforeUnmount(() => {
    source?.close()
  })

  return { lines, isConnected }
}
```

`ui/src/modules/runs/presentation/components/LiveLogPanel.vue`:

```vue
<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useLiveLog } from '@/modules/runs/presentation/composables/useLiveLog'
import { Badge } from '@/shared/components/ui/badge'

const { lines, isConnected } = useLiveLog()
const panel = ref<HTMLElement | null>(null)

watch(lines, async () => {
  await nextTick()
  if (panel.value !== null) {
    panel.value.scrollTop = panel.value.scrollHeight
  }
})
</script>

<template>
  <section aria-labelledby="live-log-heading">
    <div class="flex items-center gap-2">
      <h2 id="live-log-heading" class="text-subheading">Live logs</h2>
      <Badge>{{ isConnected ? 'Connected' : 'Disconnected' }}</Badge>
    </div>
    <div
      ref="panel"
      role="log"
      aria-live="off"
      class="mt-2 h-64 overflow-auto rounded-lg border border-line bg-surface-subtle p-3 font-mono text-code"
    >
      <p v-for="(line, index) in lines" :key="index" class="break-all whitespace-pre-wrap">
        {{ line }}
      </p>
    </div>
  </section>
</template>
```

`ui/src/modules/runs/presentation/components/RunForm.vue`:

```vue
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { RunOptions } from '@/modules/runs/domain/entities/Run'
import { Button } from '@/shared/components/ui/button'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

const props = defineProps<{ options: RunOptions; isRunning: boolean }>()
const emit = defineEmits<{ start: [keywords: string[], sites: string[]] }>()

const keywordText = ref('')
const pickedSites = ref<string[]>([])

const keywords = computed(() =>
  keywordText.value
    .split(',')
    .map((keyword) => keyword.trim())
    .filter((keyword) => keyword !== ''),
)
const canStart = computed(
  () => keywords.value.length > 0 && pickedSites.value.length > 0 && !props.isRunning,
)

watch(
  () => props.options,
  (options) => {
    keywordText.value = options.keywords.join(', ')
    pickedSites.value = options.sites.filter((site) => site.isEnabled).map((site) => site.name)
  },
  { immediate: true },
)

function setSite(name: string, isPicked: boolean | 'indeterminate'): void {
  pickedSites.value =
    isPicked === true
      ? [...pickedSites.value, name]
      : pickedSites.value.filter((site) => site !== name)
}
</script>

<template>
  <form class="flex flex-col gap-4" @submit.prevent="emit('start', keywords, pickedSites)">
    <div class="flex flex-col gap-2">
      <Label for="keywords">Keywords, separated by commas</Label>
      <Input id="keywords" v-model="keywordText" />
    </div>
    <fieldset class="flex flex-col gap-2">
      <legend class="text-body-sm font-semibold">Sites</legend>
      <div class="flex flex-wrap gap-4">
        <div v-for="site in options.sites" :key="site.name" class="flex items-center gap-2">
          <Checkbox
            :id="`site-${site.name}`"
            :model-value="pickedSites.includes(site.name)"
            @update:model-value="setSite(site.name, $event)"
          />
          <Label :for="`site-${site.name}`">{{ site.name }}</Label>
        </div>
      </div>
    </fieldset>
    <div>
      <Button type="submit" :disabled="!canStart">
        {{ isRunning ? 'Scrape running' : 'Run scrape' }}
      </Button>
    </div>
  </form>
</template>
```

`ui/src/modules/runs/presentation/components/RunHistory.vue`:

```vue
<script setup lang="ts">
import type { RunRecord } from '@/modules/runs/domain/entities/Run'
import { Badge } from '@/shared/components/ui/badge'

defineProps<{ runs: RunRecord[] }>()
const emit = defineEmits<{ select: [id: string] }>()
</script>

<template>
  <section aria-labelledby="run-history-heading">
    <h2 id="run-history-heading" class="text-subheading">History</h2>
    <p v-if="runs.length === 0" class="mt-2 text-body-sm text-ink-muted">No runs yet</p>
    <ul class="mt-2 flex flex-col divide-y divide-line">
      <li v-for="run in runs" :key="run.id">
        <button
          type="button"
          class="flex w-full items-center gap-3 py-2 text-left"
          @click="emit('select', run.id)"
        >
          <Badge>{{ run.status }}</Badge>
          <span class="text-body-sm">{{ run.keywords.join(', ') }}</span>
          <span class="ml-auto text-caption text-ink-muted">
            {{ run.jobCount }} jobs, {{ new Date(run.startedAt).toLocaleString() }}
          </span>
        </button>
      </li>
    </ul>
  </section>
</template>
```

`ui/src/modules/runs/presentation/components/RunResults.vue`:

```vue
<script setup lang="ts">
import type { RunDetail } from '@/modules/runs/domain/entities/Run'

defineProps<{ detail: RunDetail }>()
</script>

<template>
  <section aria-labelledby="run-results-heading">
    <h2 id="run-results-heading" class="text-subheading">
      Results: {{ detail.record.jobCount }} jobs
    </h2>
    <p v-if="detail.record.error" role="alert" class="mt-2 text-body-sm">
      {{ detail.record.error }}
    </p>
    <ul v-if="detail.failures.length > 0" class="mt-2 text-body-sm">
      <li v-for="failure in detail.failures" :key="`${failure.keyword}-${failure.site}`">
        {{ failure.site }}, {{ failure.keyword }}: {{ failure.reason }}
      </li>
    </ul>
    <ul class="mt-2 flex flex-col divide-y divide-line">
      <li v-for="(job, index) in detail.jobs" :key="index" class="py-2">
        <a
          v-if="job.url"
          :href="job.url"
          target="_blank"
          rel="noopener noreferrer"
          class="text-body-sm font-semibold"
        >
          {{ job.title }}
        </a>
        <p v-else class="text-body-sm font-semibold">{{ job.title }}</p>
        <p class="text-caption text-ink-muted">
          {{ job.site }}, {{ job.company }}, {{ job.location }}
        </p>
      </li>
    </ul>
  </section>
</template>
```

`ui/src/modules/runs/presentation/pages/RunsPage.vue`:

```vue
<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import LiveLogPanel from '@/modules/runs/presentation/components/LiveLogPanel.vue'
import RunForm from '@/modules/runs/presentation/components/RunForm.vue'
import RunHistory from '@/modules/runs/presentation/components/RunHistory.vue'
import RunResults from '@/modules/runs/presentation/components/RunResults.vue'
import { useRunStore } from '@/modules/runs/presentation/stores/useRunStore'
import { Skeleton } from '@/shared/components/ui/skeleton'

const store = useRunStore()

onMounted(() => void store.load())
onBeforeUnmount(() => store.stopPolling())
</script>

<template>
  <div class="flex flex-col gap-8">
    <h1 class="text-title">Runs</h1>
    <Skeleton v-if="store.status === 'loading'" class="h-40" />
    <p v-else-if="store.status === 'error'" role="alert">{{ store.errorMessage }}</p>
    <template v-else-if="store.options">
      <p v-if="store.options.isStale" class="text-body-sm text-ink-muted">
        The scraper is busy, so this list may be out of date
      </p>
      <RunForm
        :options="store.options"
        :is-running="store.isRunning"
        @start="(keywords, sites) => store.start(keywords, sites)"
      />
      <p v-if="store.startError" role="alert" class="text-body-sm">{{ store.startError }}</p>
    </template>
    <LiveLogPanel />
    <RunResults v-if="store.selected" :detail="store.selected" />
    <RunHistory :runs="store.runs" @select="store.select" />
  </div>
</template>
```

- [ ] **Step 8: Commit**

```bash
git add ui/src/modules/runs
git commit -m "feat: add runs page to scraper UI"
```

## Task 14: Config module

**Files:**
- Create: `ui/src/modules/config/domain/entities/ScraperConfig.ts`
- Create: `ui/src/modules/config/domain/repositories/ConfigRepository.ts`
- Create: `ui/src/modules/config/domain/usecases/{GetConfigUseCase,SaveConfigUseCase}.ts`
- Create: `ui/src/modules/config/data/repositories/ConfigRepositoryImpl.ts`
- Create: `ui/src/modules/config/presentation/stores/{configUseCases,useConfigStore}.ts`
- Create: `ui/src/modules/config/presentation/pages/ConfigPage.vue`
- Create: `ui/src/modules/config/routes.ts`
- Test: `ui/src/modules/config/presentation/stores/__tests__/useConfigStore.spec.ts`, `ui/src/modules/config/domain/entities/__tests__/ScraperConfig.spec.ts`

- [ ] **Step 1: Write the failing tests**

`ui/src/modules/config/domain/entities/__tests__/ScraperConfig.spec.ts`:

```ts
import { describe, expect, it } from 'vitest'
import {
  toConfigChanges,
  type ConfigSnapshot,
} from '@/modules/config/domain/entities/ScraperConfig'

const SNAPSHOT: ConfigSnapshot = {
  values: {
    keywords: ['django'],
    limit: 3,
    maxAgeHours: 72,
    proxyUrl: null,
    sites: [{ name: 'upwork', isEnabled: true, limit: 30 }],
  },
  isReadOnly: false,
  locked: ['proxy', 'sites.upwork.limit'],
  isStale: false,
}

describe('toConfigChanges', () => {
  it('leaves out locked fields', () => {
    const changes = toConfigChanges(SNAPSHOT.values, SNAPSHOT.locked)

    expect(changes.proxy_url).toBeUndefined()
    expect(changes.sites?.upwork).toEqual({ enabled: true })
  })

  it('keeps unlocked fields', () => {
    const changes = toConfigChanges(SNAPSHOT.values, [])

    expect(changes.keywords).toEqual(['django'])
    expect(changes.proxy_url).toBeNull()
    expect(changes.sites?.upwork).toEqual({ enabled: true, limit: 30 })
  })

  it('leaves out empty limits', () => {
    const values = {
      ...SNAPSHOT.values,
      limit: null,
      sites: [{ name: 'upwork', isEnabled: true, limit: null }],
    }

    const changes = toConfigChanges(values, [])

    expect('limit' in changes).toBe(false)
    expect(changes.sites?.upwork).toEqual({ enabled: true })
  })
})
```

`ui/src/modules/config/presentation/stores/__tests__/useConfigStore.spec.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
import { provideConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'

const getConfig = { execute: vi.fn() }
const saveConfig = { execute: vi.fn() }

const SNAPSHOT: ConfigSnapshot = {
  values: { keywords: ['django'], limit: 3, maxAgeHours: 72, proxyUrl: null, sites: [] },
  isReadOnly: false,
  locked: [],
  isStale: false,
}

describe('useConfigStore', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    provideConfigUseCases({ getConfig, saveConfig })
  })

  it('loads a copy of the values', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const store = useConfigStore()

    await store.load()

    expect(store.status).toBe('ready')
    expect(store.values).toEqual(SNAPSHOT.values)
    expect(store.values).not.toBe(SNAPSHOT.values)
  })

  it('shows an error when load fails', async () => {
    getConfig.execute.mockRejectedValue(new Error('Scraper down'))
    const store = useConfigStore()

    await store.load()

    expect(store.status).toBe('error')
    expect(store.errorMessage).toBe('Scraper down')
  })

  it('saves then reloads', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    saveConfig.execute.mockResolvedValue(undefined)
    const store = useConfigStore()
    await store.load()

    await expect(store.save()).resolves.toBe(true)

    expect(saveConfig.execute).toHaveBeenCalledTimes(1)
    expect(getConfig.execute).toHaveBeenCalledTimes(2)
  })

  it('keeps the message when save fails', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    saveConfig.execute.mockRejectedValue(new Error('Bad config'))
    const store = useConfigStore()
    await store.load()

    await expect(store.save()).resolves.toBe(false)

    expect(store.saveError).toBe('Bad config')
  })

  it('does not save read-only config', async () => {
    getConfig.execute.mockResolvedValue({ ...SNAPSHOT, isReadOnly: true })
    const store = useConfigStore()
    await store.load()

    await expect(store.save()).resolves.toBe(false)

    expect(saveConfig.execute).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ui && bun run test:unit --run src/modules/config`
Expected: FAIL, cannot resolve `@/modules/config/domain/entities/ScraperConfig`

- [ ] **Step 3: Write the implementation**

`ui/src/modules/config/domain/entities/ScraperConfig.ts`:

```ts
export interface SiteSetting {
  name: string
  isEnabled: boolean
  limit: number | null
}

export interface ConfigValues {
  keywords: string[]
  limit: number | null
  maxAgeHours: number | null
  proxyUrl: string | null
  sites: SiteSetting[]
}

export interface ConfigSnapshot {
  values: ConfigValues
  isReadOnly: boolean
  locked: string[]
  isStale: boolean
}

export interface ConfigChanges {
  keywords?: string[]
  limit?: number
  max_age_hours?: number
  proxy_url?: string | null
  sites?: Record<string, { enabled?: boolean; limit?: number }>
}

export function isLocked(locked: string[], path: string): boolean {
  return locked.includes(path)
}

function toSiteChanges(
  site: SiteSetting,
  locked: string[],
): { enabled?: boolean; limit?: number } {
  return {
    ...(isLocked(locked, `sites.${site.name}.enabled`) ? {} : { enabled: site.isEnabled }),
    ...(site.limit === null || isLocked(locked, `sites.${site.name}.limit`)
      ? {}
      : { limit: site.limit }),
  }
}

export function toConfigChanges(values: ConfigValues, locked: string[]): ConfigChanges {
  return {
    ...(isLocked(locked, 'keywords') ? {} : { keywords: values.keywords }),
    ...(values.limit === null || isLocked(locked, 'limit') ? {} : { limit: values.limit }),
    ...(values.maxAgeHours === null || isLocked(locked, 'max_age_hours')
      ? {}
      : { max_age_hours: values.maxAgeHours }),
    ...(isLocked(locked, 'proxy') ? {} : { proxy_url: values.proxyUrl }),
    sites: Object.fromEntries(
      values.sites.map((site) => [site.name, toSiteChanges(site, locked)]),
    ),
  }
}
```

`ui/src/modules/config/domain/repositories/ConfigRepository.ts`:

```ts
import type { ConfigChanges, ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'

export interface ConfigRepository {
  getConfig(): Promise<ConfigSnapshot>
  saveConfig(changes: ConfigChanges): Promise<void>
}
```

`ui/src/modules/config/domain/usecases/GetConfigUseCase.ts`:

```ts
import type { ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
import type { ConfigRepository } from '@/modules/config/domain/repositories/ConfigRepository'

export class GetConfigUseCase {
  private readonly repository: ConfigRepository

  constructor(repository: ConfigRepository) {
    this.repository = repository
  }

  execute(): Promise<ConfigSnapshot> {
    return this.repository.getConfig()
  }
}
```

`ui/src/modules/config/domain/usecases/SaveConfigUseCase.ts`:

```ts
import type { ConfigChanges } from '@/modules/config/domain/entities/ScraperConfig'
import type { ConfigRepository } from '@/modules/config/domain/repositories/ConfigRepository'

export class SaveConfigUseCase {
  private readonly repository: ConfigRepository

  constructor(repository: ConfigRepository) {
    this.repository = repository
  }

  execute(changes: ConfigChanges): Promise<void> {
    return this.repository.saveConfig(changes)
  }
}
```

`ui/src/modules/config/data/repositories/ConfigRepositoryImpl.ts`:

```ts
import type { HttpClient } from '@/core/http/httpClient'
import type { ConfigChanges, ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
import type { ConfigRepository } from '@/modules/config/domain/repositories/ConfigRepository'

interface ConfigModel {
  values: {
    keywords: string[]
    limit: number | null
    max_age_hours: number | null
    proxy_url: string | null
    sites: { name: string; enabled: boolean; limit: number | null }[]
  }
  read_only: boolean
  locked: string[]
  is_stale: boolean
}

function toSnapshot(model: ConfigModel): ConfigSnapshot {
  return {
    values: {
      keywords: model.values.keywords,
      limit: model.values.limit,
      maxAgeHours: model.values.max_age_hours,
      proxyUrl: model.values.proxy_url,
      sites: model.values.sites.map((site) => ({
        name: site.name,
        isEnabled: site.enabled,
        limit: site.limit,
      })),
    },
    isReadOnly: model.read_only,
    locked: model.locked,
    isStale: model.is_stale,
  }
}

export class ConfigRepositoryImpl implements ConfigRepository {
  private readonly client: HttpClient

  constructor(client: HttpClient) {
    this.client = client
  }

  async getConfig(): Promise<ConfigSnapshot> {
    return toSnapshot(await this.client.get<ConfigModel>('/config'))
  }

  saveConfig(changes: ConfigChanges): Promise<void> {
    return this.client.put<void>('/config', changes)
  }
}
```

`ui/src/modules/config/routes.ts`:

```ts
import { httpClient } from '@/core/http/httpClient'
import { ConfigRepositoryImpl } from '@/modules/config/data/repositories/ConfigRepositoryImpl'
import { GetConfigUseCase } from '@/modules/config/domain/usecases/GetConfigUseCase'
import { SaveConfigUseCase } from '@/modules/config/domain/usecases/SaveConfigUseCase'
import type { ConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'

export function createConfigUseCases(): ConfigUseCases {
  const repository = new ConfigRepositoryImpl(httpClient)
  return {
    getConfig: new GetConfigUseCase(repository),
    saveConfig: new SaveConfigUseCase(repository),
  }
}
```

`ui/src/modules/config/presentation/stores/configUseCases.ts`:

```ts
import type { GetConfigUseCase } from '@/modules/config/domain/usecases/GetConfigUseCase'
import type { SaveConfigUseCase } from '@/modules/config/domain/usecases/SaveConfigUseCase'

export interface ConfigUseCases {
  getConfig: Pick<GetConfigUseCase, 'execute'>
  saveConfig: Pick<SaveConfigUseCase, 'execute'>
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

`ui/src/modules/config/presentation/stores/useConfigStore.ts`:

```ts
import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  toConfigChanges,
  type ConfigSnapshot,
  type ConfigValues,
} from '@/modules/config/domain/entities/ScraperConfig'
import { requireConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'
import type { LoadStatus } from '@/shared/utils/loadStatus'

const FALLBACK_ERROR_MESSAGE = 'Something went wrong. Try again.'

function toMessage(error: unknown): string {
  return error instanceof Error ? error.message : FALLBACK_ERROR_MESSAGE
}

function copyValues(values: ConfigValues): ConfigValues {
  return {
    ...values,
    keywords: [...values.keywords],
    sites: values.sites.map((site) => ({ ...site })),
  }
}

export const useConfigStore = defineStore('config', () => {
  const status = ref<LoadStatus>('idle')
  const values = ref<ConfigValues | null>(null)
  const snapshot = ref<ConfigSnapshot | null>(null)
  const errorMessage = ref<string | null>(null)
  const saveError = ref<string | null>(null)
  const isSaving = ref(false)

  async function load(): Promise<void> {
    status.value = 'loading'
    errorMessage.value = null
    try {
      const next = await requireConfigUseCases().getConfig.execute()
      snapshot.value = next
      values.value = copyValues(next.values)
      status.value = 'ready'
    } catch (error) {
      errorMessage.value = toMessage(error)
      status.value = 'error'
    }
  }

  async function save(): Promise<boolean> {
    const current = values.value
    const loaded = snapshot.value
    if (current === null || loaded === null || loaded.isReadOnly) {
      return false
    }
    isSaving.value = true
    saveError.value = null
    try {
      await requireConfigUseCases().saveConfig.execute(toConfigChanges(current, loaded.locked))
      await load()
      return true
    } catch (error) {
      saveError.value = toMessage(error)
      return false
    } finally {
      isSaving.value = false
    }
  }

  return { status, values, snapshot, errorMessage, saveError, isSaving, load, save }
})
```

`ui/src/modules/config/presentation/pages/ConfigPage.vue`:

```vue
<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { isLocked } from '@/modules/config/domain/entities/ScraperConfig'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import { Button } from '@/shared/components/ui/button'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Skeleton } from '@/shared/components/ui/skeleton'

const SAVED_MESSAGE = 'Config saved'

const store = useConfigStore()
const isReadOnly = computed(() => store.snapshot?.isReadOnly ?? true)
const locked = computed(() => store.snapshot?.locked ?? [])

const keywordText = computed({
  get: () => store.values?.keywords.join(', ') ?? '',
  set: (text: string) => {
    if (store.values !== null) {
      store.values.keywords = text
        .split(',')
        .map((keyword) => keyword.trim())
        .filter((keyword) => keyword !== '')
    }
  },
})

const proxyText = computed({
  get: () => store.values?.proxyUrl ?? '',
  set: (text: string) => {
    if (store.values !== null) {
      store.values.proxyUrl = text.trim() === '' ? null : text.trim()
    }
  },
})

function isFieldDisabled(path: string): boolean {
  return isReadOnly.value || isLocked(locked.value, path)
}

async function save(): Promise<void> {
  if (await store.save()) {
    toast.success(SAVED_MESSAGE)
  }
}

onMounted(() => void store.load())
</script>

<template>
  <div class="flex flex-col gap-6">
    <h1 class="text-title">Config</h1>
    <Skeleton v-if="store.status === 'loading'" class="h-40" />
    <p v-else-if="store.status === 'error'" role="alert">{{ store.errorMessage }}</p>
    <form v-else-if="store.values" class="flex flex-col gap-5" @submit.prevent="save">
      <p v-if="isReadOnly" class="text-body-sm text-ink-muted">
        Read-only here. Change config through git and deploy
      </p>
      <p v-if="locked.length > 0" class="text-body-sm text-ink-muted">
        Disabled fields are set by config.dev.patch.yaml
      </p>
      <p v-if="store.snapshot?.isStale" class="text-body-sm text-ink-muted">
        The scraper is busy, so these values may be out of date
      </p>
      <div class="flex flex-col gap-2">
        <Label for="keywords">Keywords, separated by commas</Label>
        <Input id="keywords" v-model="keywordText" :disabled="isFieldDisabled('keywords')" />
      </div>
      <div class="flex flex-col gap-2">
        <Label for="limit">Limit per site</Label>
        <Input
          id="limit"
          v-model.number="store.values.limit"
          type="number"
          min="1"
          :disabled="isFieldDisabled('limit')"
        />
      </div>
      <div class="flex flex-col gap-2">
        <Label for="max-age">Max job age in hours</Label>
        <Input
          id="max-age"
          v-model.number="store.values.maxAgeHours"
          type="number"
          min="1"
          :disabled="isFieldDisabled('max_age_hours')"
        />
      </div>
      <div class="flex flex-col gap-2">
        <Label for="proxy">Proxy URL</Label>
        <Input id="proxy" v-model="proxyText" :disabled="isFieldDisabled('proxy')" />
      </div>
      <fieldset class="flex flex-col gap-3">
        <legend class="text-body-sm font-semibold">Sites</legend>
        <div v-for="site in store.values.sites" :key="site.name" class="flex items-center gap-3">
          <Checkbox
            :id="`config-site-${site.name}`"
            :model-value="site.isEnabled"
            :disabled="isFieldDisabled(`sites.${site.name}.enabled`)"
            @update:model-value="site.isEnabled = $event === true"
          />
          <Label :for="`config-site-${site.name}`" class="w-28">{{ site.name }}</Label>
          <Input
            v-model.number="site.limit"
            type="number"
            min="1"
            class="w-24"
            :aria-label="`${site.name} limit`"
            :disabled="isFieldDisabled(`sites.${site.name}.limit`)"
          />
        </div>
      </fieldset>
      <p v-if="store.saveError" role="alert" class="text-body-sm">{{ store.saveError }}</p>
      <div v-if="!isReadOnly">
        <Button type="submit" :disabled="store.isSaving">Save</Button>
      </div>
    </form>
  </div>
</template>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ui && bun run test:unit --run src/modules/config`
Expected: `8 passed`

- [ ] **Step 5: Run all UI tests and the build**

Run: `cd ui && bun run test:unit --run`
Expected: all tests pass

Run: `cd ui && bun run build`
Expected: type-check passes and `ui/dist/index.html` exists. If `vue-tsc` rejects `number | null` on `Input`, bind those fields with `:model-value="value ?? ''"` plus `@update:model-value` that stores `null` for an empty string and `Number(value)` otherwise

- [ ] **Step 6: Commit**

```bash
git add ui
git commit -m "feat: add config page to scraper UI"
```

---

# Part C: Dev stack

## Task 15: Docker image

**Files:**
- Modify: `Dockerfile`, `.dockerignore`, `.gitignore`

- [ ] **Step 1: Create log folder in the runtime image**

A new named volume copies owner from the image folder, so `/app/logs` must exist. In `Dockerfile`, change the `runtime-base` lines to:

```dockerfile
RUN mkdir -p /app/output /app/logs \
 && chown -R pwuser:pwuser /app
```

- [ ] **Step 2: Add UI stages before the `bot` stage**

```dockerfile
# =============================================================================
# STAGE: ui-build — compiles the Vue app into ui/dist
# =============================================================================
FROM oven/bun:1.4.4-slim AS bun-binary

FROM node:24-slim AS ui-build

COPY --from=bun-binary /usr/local/bin/bun /usr/local/bin/bun
WORKDIR /ui
COPY ui/package.json ui/bun.lock ./
RUN bun install --frozen-lockfile
COPY ui/ ./
RUN bun run build


# =============================================================================
# STAGE: ui-server — FastAPI service that also serves the Vue build, port 8090
# =============================================================================
FROM python:3.13-slim AS ui-server

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --uid 1001 --create-home uiuser \
 && mkdir -p /app/output /app/logs /app/config-backups \
 && chown -R uiuser:uiuser /app

WORKDIR /app

COPY ui_server/requirements.txt ./ui-requirements.txt
RUN pip install --no-cache-dir -r ui-requirements.txt

COPY --chown=uiuser:uiuser scraper/__init__.py scraper/config_loader.py scraper/types.py ./scraper/
COPY --chown=uiuser:uiuser ui_server ./ui_server
COPY --chown=uiuser:uiuser --from=ui-build /ui/dist ./ui/dist

USER uiuser

EXPOSE 8090

ENTRYPOINT ["python", "-m", "ui_server"]
CMD []
```

- [ ] **Step 3: Keep build context clean**

Add to `.dockerignore`:

```text
ui/node_modules
ui/dist
config-backups
logs
.delta
```

Add to `.gitignore`, under `# Project-specific scraper artifacts`:

```text
config-backups/
ui/node_modules/
```

- [ ] **Step 4: Build and smoke-test the image**

Run: `docker build --target ui-server -t job-scraper-ui:latest .`
Expected: build succeeds

Run: `docker run --rm --entrypoint python job-scraper-ui:latest -c "from ui_server.app import create_app; print(create_app().title)"`
Expected: prints `Scraper UI`

Run: `docker build --target mcp-server -t job-scraper-mcp:latest .`
Expected: build succeeds, image now has `scraper/sites/upwork.py`

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore .gitignore
git commit -m "feat: add scraper UI Docker image"
```

## Task 16: Dev compose

**Files:**
- Modify: `docker-compose.yml`, `docker-compose.dev.yml`, `scripts/run_dev.sh`, `.env.example`

- [ ] **Step 1: Update base compose**

In `docker-compose.yml`, replace the `output-init` entrypoint so run folders belong to the UI user:

```yaml
    entrypoint:
      [
        "sh",
        "-c",
        "mkdir -p /out/ui-runs && chown -R pwuser:pwuser /out && chown -R ${UI_UID:-1001}:${UI_GID:-1001} /out/ui-runs",
      ]
```

Add the log volume to `scraper-mcp`, under `volumes`:

```yaml
      - scraper-logs:/app/logs
```

Add the UI service after `scraper-mcp`:

```yaml
  # SERVICE: scraper-ui — FastAPI + Vue control panel; profile-gated, needs scraper-mcp running
  scraper-ui:
    build:
      context: .
      dockerfile: Dockerfile
      target: ui-server
    image: job-scraper-ui:latest
    container_name: job-scraper-ui
    restart: unless-stopped
    profiles: ["ui"]
    depends_on:
      output-init:
        condition: service_completed_successfully
    healthcheck:
      test:
        [
          "CMD",
          "python",
          "-c",
          "import urllib.request; urllib.request.urlopen('http://localhost:8090/health')",
        ]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 10s
    volumes:
      - ./output:/app/output
      - scraper-logs:/app/logs:ro
```

Add under the top-level `volumes`:

```yaml
  scraper-logs:
```

- [ ] **Step 2: Update dev compose**

Add to `docker-compose.dev.yml`:

```yaml
  # override: run as the host user so config.yaml stays writable; local access only
  scraper-ui:
    user: "${UI_UID:-1001}:${UI_GID:-1001}"
    ports:
      - "127.0.0.1:8090:8090"
    environment:
      - UI_ENV=dev
      - UI_MCP_URL=http://scraper-mcp:8080/mcp
    volumes:
      - ./config.yaml:/app/config.yaml
      - ./config.dev.patch.yaml:/app/config.dev.patch.yaml:ro
      - /tmp/config.dev.yaml:/app/config.dev.yaml
      - ./config-backups:/app/config-backups
```

- [ ] **Step 3: Update `scripts/run_dev.sh`**

Change usage comments:

```bash
#   ./scripts/run_dev.sh           # mcp + bot + ui
#   ./scripts/run_dev.sh mcp       # MCP server only
#   ./scripts/run_dev.sh bot       # bot only
#   ./scripts/run_dev.sh ui        # MCP server + UI at http://127.0.0.1:8090
```

Add after `# --- merge config ---` block:

```bash
# --- ui file access ---
# scraper-ui edits host-owned config files, so it runs as the host user in dev.
export UI_UID="$(id -u)" UI_GID="$(id -g)"
mkdir -p "$REPO_ROOT/config-backups"
```

Change the profiles case:

```bash
case "$ARG" in
  mcp)  PROFILES="--profile mcp" ;;
  bot)  PROFILES="--profile bot" ;;
  ui)   PROFILES="--profile mcp --profile ui" ;;
  all)  PROFILES="--profile mcp --profile bot --profile ui" ;;
  *)
    echo "Usage: $0 [mcp|bot|ui]" >&2
    exit 1
    ;;
esac
```

- [ ] **Step 4: Update `.env.example`**

Add:

```bash
# Host user for scraper-ui in dev, so it can edit config.yaml. scripts/run_dev.sh sets
# these for you. Set them here when you start the stack another way, such as scripts/manage.py.
UI_UID=1000
UI_GID=1000
```

- [ ] **Step 5: Validate compose**

Run: `MONGO_ROOT_PASSWORD=x docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile mcp --profile ui config --quiet`
Expected: exit code 0, no output

- [ ] **Step 6: Start the stack**

Run: `./scripts/run_dev.sh ui`
Expected: `job-scraper-mcp` and `job-scraper-ui` both become healthy

Run: `docker ps --filter name=job-scraper --format '{{.Names}} {{.Status}}'`
Expected: both show `(healthy)`

- [ ] **Step 7: Verify in the browser**

Open `http://127.0.0.1:8090` in the built-in browser and check each item:

1. Runs page loads and lists `upwork`
2. Pick `upwork`, enter `software engineer`, press Run scrape
3. Live logs show `[upwork:software-engineer] api returned`
4. Run ends, status `succeeded`, jobs listed
5. `output/ui-runs/<run_id>/result.json` exists
6. Second press during a run shows `A scrape is already running.`
7. Config page shows `keywords` and `proxy` disabled, because `config.dev.patch.yaml` sets them
8. Change Limit, save, confirm `config.yaml` changed, its comments stayed, `config-backups/` has one file, and `/tmp/config.dev.yaml` has the new value
9. `grep -rn "ui_server" ../frontend/src ../backend/src` returns nothing, and `git -C ../frontend status` and `git -C ../backend status` show no new changes from this work

Take a screenshot of the finished run for the record

- [ ] **Step 8: Commit**

```bash
git add docker-compose.yml docker-compose.dev.yml scripts/run_dev.sh .env.example
git commit -m "feat: run scraper UI in dev compose"
```

---

# Part D: Prod

## Task 17: Caddy

**Files:**
- Create: `Caddyfile`

- [ ] **Step 1: Add the Caddyfile**

`Caddyfile`:

```caddyfile
{$UI_DOMAIN} {
	encode zstd gzip

	header {
		Strict-Transport-Security "max-age=31536000; includeSubDomains"
		X-Content-Type-Options "nosniff"
		X-Frame-Options "DENY"
		Referrer-Policy "strict-origin-when-cross-origin"
		Permissions-Policy "camera=(), microphone=(), geolocation=()"
		Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
		-Server
	}

	reverse_proxy scraper-ui:8090 {
		flush_interval -1
	}
}
```

`flush_interval -1` keeps the live log stream from being buffered

- [ ] **Step 2: Validate**

Run: `docker run --rm -e UI_DOMAIN=example.com -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile`
Expected: `Valid configuration`

- [ ] **Step 3: Commit**

```bash
git add Caddyfile
git commit -m "feat: add Caddy config for scraper UI"
```

## Task 18: Add password helper docs

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Document prod values**

Add to `.env.example`:

```bash
# Prod scraper-ui only. Production values come from GitHub secrets and vars, not this file.
# Make the password hash and put it in the UI_PASSWORD_HASH secret:
#   .venv/bin/python -c "from argon2 import PasswordHasher; import getpass; print(PasswordHasher().hash(getpass.getpass()))"
# Make the session secret and put it in the UI_SESSION_SECRET secret:
#   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# If you place the hash in a local .env, wrap it in single quotes, because it contains $.
UI_PASSWORD_HASH=
UI_SESSION_SECRET=
UI_DOMAIN=
# Prod scraper-mcp bind address. Default is the Docker gateway, so bot and scraper-ui
# reach it through host.docker.internal and the public cannot.
MCP_BIND_HOST=172.17.0.1
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: list scraper UI prod settings"
```

## Task 19: Prod compose

**Files:**
- Modify: `docker-compose.prod.yml`, `scripts/run_prod.sh`

- [ ] **Step 1: Confirm the current failure**

Run: `MONGO_ROOT_PASSWORD=x docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile mcp config --quiet`
Expected: FAIL with `service scraper-mcp declares mutually exclusive network_mode and networks`

- [ ] **Step 2: Update prod compose**

Replace the `scraper-mcp` block and add the new services in `docker-compose.prod.yml`:

```yaml
services:

  # override: use pre-built image from ghcr.io; host networking gives access to
  # localhost:1080 (reverse SSH proxy tunnel) and localhost:27017 (mongo published port).
  # MONGO_URI must point to localhost (not 'mongo' DNS which is bridge-only).
  # MCP_HOST is the Docker gateway: containers reach it through host.docker.internal,
  # and the public cannot. Do not use 127.0.0.1, it would cut off the bot.
  scraper-mcp:
    image: ${MCP_IMAGE:-job-scraper-mcp:latest}
    network_mode: host
    networks: !reset []
    ports: !reset []
    healthcheck:
      test: ["CMD", "curl", "-f", "http://${MCP_BIND_HOST:-172.17.0.1}:8080/health"]
    environment:
      - MONGO_URI=mongodb://${MONGO_ROOT_USER:-admin}:${MONGO_ROOT_PASSWORD}@localhost:27017
      - MCP_HOST=${MCP_BIND_HOST:-172.17.0.1}

  # override: use pre-built image from ghcr.io
  bot:
    image: ${BOT_IMAGE:-job-scraper-bot:latest}

  # override: pre-built image; reached only through caddy, so no published port
  scraper-ui:
    image: ${UI_IMAGE:-job-scraper-ui:latest}
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      - UI_ENV=prod
      - UI_MCP_URL=http://host.docker.internal:8080/mcp
      - UI_PASSWORD_HASH=${UI_PASSWORD_HASH:-}
      - UI_SESSION_SECRET=${UI_SESSION_SECRET:-}
      - FORWARDED_ALLOW_IPS=*

  # SERVICE: caddy — public HTTPS entry for scraper-ui; certificates renew automatically
  caddy:
    image: caddy:2-alpine
    container_name: job-scraper-caddy
    restart: unless-stopped
    profiles: ["ui"]
    depends_on:
      - scraper-ui
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    environment:
      - UI_DOMAIN=${UI_DOMAIN:-}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
      - caddy-config:/config

volumes:
  caddy-data:
  caddy-config:
```

`FORWARDED_ALLOW_IPS=*` is safe here only because `scraper-ui` has no published port. Caddy is its only client, so `X-Forwarded-For` cannot be forged from outside

- [ ] **Step 3: Validate prod compose**

Run: `MONGO_ROOT_PASSWORD=x docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile mcp --profile ui config --quiet`
Expected: exit code 0

Run: `MONGO_ROOT_PASSWORD=x docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile mcp config | grep -E 'MCP_HOST|network_mode'`
Expected: shows `MCP_HOST: 172.17.0.1` and `network_mode: host`

- [ ] **Step 4: Add `ui` to `scripts/run_prod.sh`**

Change the usage comments and case:

```bash
#   ./scripts/run_prod.sh           # both mcp + bot
#   ./scripts/run_prod.sh mcp       # MCP server only
#   ./scripts/run_prod.sh bot       # bot only
#   ./scripts/run_prod.sh ui        # MCP server + UI + Caddy (needs UI_* values in .env)
```

```bash
case "$ARG" in
  mcp)  PROFILES="--profile mcp" ;;
  bot)  PROFILES="--profile bot" ;;
  ui)   PROFILES="--profile mcp --profile ui" ;;
  all)  PROFILES="--profile mcp --profile bot" ;;
  *)
    echo "Usage: $0 [mcp|bot|ui]" >&2
    exit 1
    ;;
esac
```

- [ ] **Step 5: Test prod mode locally without Caddy**

Run:

```bash
docker run --rm -p 127.0.0.1:8091:8090 -e UI_ENV=prod -e UI_PASSWORD_HASH='wrong' job-scraper-ui:latest
```

Expected: container exits with an error that names `UI_SESSION_SECRET`. This proves prod refuses to start without its secrets

- [ ] **Step 6: Commit**

```bash
git add docker-compose.prod.yml scripts/run_prod.sh
git commit -m "fix: make prod compose valid and add scraper UI"
```

## Task 20: Deploy workflow

**Files:**
- Modify: `.github/workflows/deploy.yml`, `docs/deploy.md`, `README.md`

- [ ] **Step 1: Add build job**

Add after `build-bot` in `.github/workflows/deploy.yml`:

```yaml
  # 2b. Build scraper UI Docker image and push to ghcr.io
  build-ui:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    outputs:
      image_tag_sha: ${{ steps.tags.outputs.sha }}
    steps:
      - uses: actions/checkout@v4

      - name: Set image tags
        id: tags
        run: |
          # ghcr.io requires lowercase; github.repository may contain uppercase chars
          REPO_LOWER=$(echo '${{ github.repository }}' | tr '[:upper:]' '[:lower:]')
          # rolling tag — always points to the newest build
          echo "latest=ghcr.io/${REPO_LOWER}:ui-latest" >> "$GITHUB_OUTPUT"
          # immutable tag pinned to this exact commit, used for deployment
          echo "sha=ghcr.io/${REPO_LOWER}:ui-${{ github.sha }}" >> "$GITHUB_OUTPUT"

      - name: Login to ghcr.io
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build & push scraper-ui image
        uses: docker/build-push-action@v5
        with:
          context: .
          target: ui-server
          push: true
          cache-from: type=gha,scope=ui
          cache-to: type=gha,mode=max,scope=ui
          tags: |
            ${{ steps.tags.outputs.latest }}
            ${{ steps.tags.outputs.sha }}
```

- [ ] **Step 2: Create `job-net` on deploy**

`mongo` needs the external `job-net` network. In the `deploy-mcp` script, add before `C="docker compose ...`:

```bash
            docker network inspect job-net >/dev/null 2>&1 || docker network create job-net
```

Add `MCP_BIND_HOST` to `envs:` in `deploy-mcp` and `deploy-bot`, and to each `env:` block:

```yaml
          MCP_BIND_HOST: ${{ vars.MCP_BIND_HOST || '172.17.0.1' }}
```

- [ ] **Step 3: Add deploy job**

Add at the end of the file:

```yaml
  # 5. SSH into VPS → pull new UI image → restart UI and Caddy (runs after build-ui + deploy-bot)
  deploy-ui:
    needs: [build-ui, deploy-bot]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Ensure deploy dir
        uses: appleboy/ssh-action@v1.2.0
        with:
          host: ${{ secrets.SSH_HOST }}
          username: ${{ secrets.SSH_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: mkdir -p ~/scraper

      - name: Copy compose files
        uses: appleboy/scp-action@v0.1.7
        with:
          host: ${{ secrets.SSH_HOST }}
          username: ${{ secrets.SSH_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          source: "docker-compose.yml,docker-compose.prod.yml,Caddyfile"
          target: "~/scraper"

      - name: Deploy scraper-ui
        uses: appleboy/ssh-action@v1.2.0
        with:
          host: ${{ secrets.SSH_HOST }}
          username: ${{ secrets.SSH_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          envs: UI_IMAGE,UI_PASSWORD_HASH,UI_SESSION_SECRET,UI_DOMAIN,MCP_BIND_HOST
          script: |
            set -euo pipefail
            cd ~/scraper

            C="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
            $C --profile ui pull
            $C --profile ui up -d --no-build
            $C ps
        env:
          UI_IMAGE: ${{ needs.build-ui.outputs.image_tag_sha }}
          UI_PASSWORD_HASH: ${{ secrets.UI_PASSWORD_HASH }}
          UI_SESSION_SECRET: ${{ secrets.UI_SESSION_SECRET }}
          UI_DOMAIN: ${{ vars.UI_DOMAIN }}
          MCP_BIND_HOST: ${{ vars.MCP_BIND_HOST || '172.17.0.1' }}
```

- [ ] **Step 4: Update docs**

In `docs/deploy.md`, replace the second paragraph under `## Networking` with:

```markdown
scraper-mcp listens on the Docker gateway address (`MCP_BIND_HOST`, default
`172.17.0.1`), so containers on the VPS can reach it through
`host.docker.internal:8080` and the public cannot. Do not set it to `127.0.0.1`,
which would cut off the bot.

scraper-ui has no published port. Caddy is its only public entry, on ports 80 and
443. Required before the first deploy: `UI_PASSWORD_HASH` and `UI_SESSION_SECRET`
secrets, a `UI_DOMAIN` variable, and a DNS record pointing to the VPS.
```

Add to `README.md`, before `# The scraping prompt (prompts/scrape-and-post.md)`:

```markdown
# Scraper UI

Web control panel for this repo: run scrapes, see results, edit config, and watch
live logs. It does not depend on the job-agent frontend or backend.

Start it in dev, then open http://127.0.0.1:8090:

    ./scripts/run_dev.sh ui

For Vue hot reload, keep the stack running and start Vite, then open
http://localhost:5174:

    cd ui && bun install && bun run dev

- Runs go through `scraper-mcp`, one at a time, with no stop button
- Each run is saved to `output/ui-runs/<run_id>/`, last 50 kept, and also to Mongo
- Dev config edits write `config.yaml` and refresh `/tmp/config.dev.yaml`. Backups go
  to `config-backups/`. Fields set in `config.dev.patch.yaml` are locked
- Prod is public through Caddy with one password. Config is read-only there
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/deploy.yml docs/deploy.md README.md
git commit -m "ci: deploy scraper UI to prod"
```

- [ ] **Step 6: Set GitHub values before merge to main**

The user does this, because it needs real secrets:

- Secrets: `UI_PASSWORD_HASH`, `UI_SESSION_SECRET`
- Variables: `UI_DOMAIN`, and `MCP_BIND_HOST` when the VPS gateway is not `172.17.0.1`

- [ ] **Step 7: Verify prod after deploy**

Run from outside the VPS: `curl -sS -o /dev/null -w '%{http_code}\n' --max-time 5 http://<vps-ip>:8080/health`
Expected: connection refused or timeout, not `200`

Run on the VPS: `docker exec job-scraper-bot curl -sf http://host.docker.internal:8080/health`
Expected: `{"status":"ok","mongo":"ok"}`

Open `https://<domain>`:

1. Login page shows, valid HTTPS certificate
2. Wrong password shows `Wrong password.`
3. After 5 wrong tries, `Too many tries. Try again in a few minutes.`
4. Right password opens Runs
5. Config page shows read-only message and no Save button
6. A run works and live logs stream

Coverage target: run `.venv/bin/pytest --cov=ui_server tests/test_ui_*.py` if `pytest-cov` is installed, and `bun run test:unit --run --coverage` in `ui/` if the coverage provider is installed. Target is 80%
