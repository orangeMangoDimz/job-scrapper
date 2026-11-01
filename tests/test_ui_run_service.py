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
