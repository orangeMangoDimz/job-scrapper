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

    def ensure_idle(self) -> None:
        if self._task is not None and not self._task.done():
            raise RunInProgressError()

    def start(self, keywords: tuple[str, ...], sites: tuple[str, ...]) -> RunRecord:
        self.ensure_idle()
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
