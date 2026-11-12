from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from ui_server.errors import (
    ConfigInvalidError,
    DiscordForbiddenError,
    DiscordNotConfiguredError,
    DiscordUnauthorizedError,
    McpUnavailableError,
    RunInProgressError,
)
from ui_server.schema.discord import MAX_JOBS, MAX_TEXT_CHARS
from ui_server.services.run_store import DiscordStatus, RunRecord, RunStore, flatten_result

LOG = logging.getLogger("scraper-ui")
RUN_FAILED_MESSAGE = "The scrape failed."
DISCORD_NO_TOKEN_MESSAGE = "Discord token is not configured."
DISCORD_NO_CHANNEL_MESSAGE = "No default Discord channel is set."
DISCORD_SEND_FAILED_MESSAGE = "Sending to Discord failed."
DISCORD_MENTION_RESERVE = 24
DISCORD_KNOWN_ERRORS = (
    DiscordNotConfiguredError,
    DiscordUnauthorizedError,
    DiscordForbiddenError,
    ConfigInvalidError,
    McpUnavailableError,
)


class Scraper(Protocol):
    async def scrape_jobs(
        self, sites: tuple[str, ...], keywords: tuple[str, ...]
    ) -> dict[str, Any]: ...

    async def read_discord_settings(self) -> dict[str, Any]: ...

    async def send_discord_message(
        self, channel_id: str, mention: bool, text: str | None, jobs: list[dict[str, Any]] | None
    ) -> dict[str, Any]: ...


def _fit_text(lead: str, tail: str = "") -> str:
    limit = MAX_TEXT_CHARS - DISCORD_MENTION_RESERVE
    kept_tail = tail[:limit]
    return lead[: limit - len(kept_tail)] + kept_tail


def _discord_text(record: RunRecord) -> str:
    keywords = ", ".join(record.keywords)
    sites = ", ".join(record.sites)
    if record.error:
        return _fit_text(f"Run failed for {keywords} on {sites}", f": {record.error}")
    return _fit_text(f"{keywords} on {sites} found 0 jobs")


def _count_kind(result: dict[str, Any], kind: str) -> tuple[int, int]:
    entries = [entry for entry in result["results"] if entry["kind"] == kind]
    failed = sum(1 for entry in entries if entry["status"] == "failed")
    return len(entries) - failed, failed


def _send_error_message(run_id: str, exc: Exception) -> str:
    if isinstance(exc, DISCORD_KNOWN_ERRORS):
        return exc.message
    LOG.error("run %s discord send failed", run_id, exc_info=exc)
    return DISCORD_SEND_FAILED_MESSAGE


def _discord_status(sent: int, failed: int) -> DiscordStatus:
    if sent == 0:
        return DiscordStatus.FAILED
    return DiscordStatus.PARTIAL if failed > 0 else DiscordStatus.SENT


class RunService:
    def __init__(self, store: RunStore, scraper: Scraper) -> None:
        self._store = store
        self._scraper = scraper
        self._task: asyncio.Task[None] | None = None

    def ensure_idle(self) -> None:
        if self._task is not None and not self._task.done():
            raise RunInProgressError()

    def start(
        self, keywords: tuple[str, ...], sites: tuple[str, ...], notify_discord: bool
    ) -> RunRecord:
        self.ensure_idle()
        record = self._store.create(keywords, sites)
        self._task = asyncio.create_task(self._execute(record, notify_discord))
        return record

    async def wait(self) -> None:
        if self._task is not None:
            await self._task

    async def _execute(self, record: RunRecord, notify_discord: bool) -> None:
        jobs: list[dict[str, Any]] = []
        try:
            result = await self._scraper.scrape_jobs(record.sites, record.keywords)
            outcome = self._store.finish(record, result)
            jobs, _ = flatten_result(result)
        except McpUnavailableError as exc:
            outcome = self._store.fail(record, exc.message)
        except Exception:
            LOG.exception("run %s failed", record.id)
            outcome = self._store.fail(record, RUN_FAILED_MESSAGE)
        if notify_discord:
            await self._notify_discord(outcome, jobs)
        self._store.prune()

    def _fail_discord(self, record: RunRecord, message: str) -> None:
        self._store.update_discord(record, DiscordStatus.FAILED, error=message)

    async def _notify_discord(self, record: RunRecord, jobs: list[dict[str, Any]]) -> None:
        sending = record
        try:
            sending = self._store.update_discord(record, DiscordStatus.SENDING)
            settings = await self._scraper.read_discord_settings()
            if not settings.get("configured"):
                self._fail_discord(sending, DISCORD_NO_TOKEN_MESSAGE)
                return
            channel_id = settings.get("default_channel_id")
            if not channel_id:
                self._fail_discord(sending, DISCORD_NO_CHANNEL_MESSAGE)
                return
            mention = bool(settings.get("mention_user_id"))
            await self._send(sending, channel_id, mention, jobs)
        except Exception:
            LOG.exception("run %s discord notify failed", record.id)
            self._guarded_fail_discord(sending, DISCORD_SEND_FAILED_MESSAGE)

    def _guarded_fail_discord(self, record: RunRecord, message: str) -> None:
        try:
            self._fail_discord(record, message)
        except Exception:
            LOG.exception("run %s discord failure not saved", record.id)

    async def _send(
        self, record: RunRecord, channel_id: str, mention: bool, jobs: list[dict[str, Any]]
    ) -> None:
        batches: list[tuple[str | None, list[dict[str, Any]] | None]]
        if jobs:
            kind = "job"
            batches = [
                (None, jobs[start : start + MAX_JOBS]) for start in range(0, len(jobs), MAX_JOBS)
            ]
        else:
            kind = "text"
            batches = [(_discord_text(record), None)]
        sent = 0
        failed = 0
        for index, (text, chunk) in enumerate(batches):
            try:
                result = await self._scraper.send_discord_message(
                    channel_id, mention and index == 0, text, chunk
                )
            except Exception as exc:
                message = _send_error_message(record.id, exc)
                status = DiscordStatus.PARTIAL if sent > 0 else DiscordStatus.FAILED
                self._store.update_discord(record, status, sent, failed, message)
                return
            chunk_sent, chunk_failed = _count_kind(result, kind)
            sent += chunk_sent
            failed += chunk_failed
        self._store.update_discord(record, _discord_status(sent, failed), sent, failed)
