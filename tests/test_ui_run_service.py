from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ui_server.errors import (
    ConfigInvalidError,
    DiscordForbiddenError,
    DiscordNotConfiguredError,
    DiscordUnauthorizedError,
    McpUnavailableError,
    RunInProgressError,
)
from ui_server.services.run_service import RunService
from ui_server.services.run_store import DiscordStatus, RunStatus, RunStore

CHANNEL_ID = "123456789012345678"
USER_ID = "223456789012345678"
DISCORD_SETTINGS = {
    "configured": True,
    "default_channel_id": CHANNEL_ID,
    "mention_user_id": USER_ID,
}


class FakeScraper:
    def __init__(self, outcome: dict | Exception) -> None:
        self._outcome = outcome
        self.release = asyncio.Event()
        self.settings: dict | Exception = DISCORD_SETTINGS
        self.send_outcomes: list[dict | Exception] = []
        self.sent_messages: list[tuple] = []

    async def scrape_jobs(self, sites: tuple[str, ...], keywords: tuple[str, ...]) -> dict:
        await self.release.wait()
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome

    async def read_discord_settings(self) -> dict:
        if isinstance(self.settings, Exception):
            raise self.settings
        return self.settings

    async def send_discord_message(
        self, channel_id: str, mention: bool, text: str | None, jobs: list[dict] | None
    ) -> dict:
        self.sent_messages.append((channel_id, mention, text, jobs))
        outcome = self.send_outcomes.pop(0) if self.send_outcomes else _default_delivery(text, jobs)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _entry(kind: str, status: str) -> dict:
    return {"index": 0, "kind": kind, "title": None, "status": status, "message_id": None}


def _delivery(sent: int, failed: int, summary_status: str = "sent") -> dict:
    results = [
        *[_entry("job", "sent")] * sent,
        *[_entry("job", "failed")] * failed,
        _entry("summary", summary_status),
    ]
    summary_failed = summary_status == "failed"
    return {
        "sent": sent + (0 if summary_failed else 1),
        "failed": failed + (1 if summary_failed else 0),
        "results": results,
    }


def _text_delivery(status: str) -> dict:
    return {
        "sent": int(status == "sent"),
        "failed": int(status == "failed"),
        "results": [_entry("text", status)],
    }


def _default_delivery(text: str | None, jobs: list[dict] | None) -> dict:
    if text is not None:
        return _text_delivery("sent")
    return _delivery(len(jobs or []), 0)


def _jobs_result(count: int) -> dict:
    jobs = [{"title": f"job {index}"} for index in range(count)]
    return {
        "ok": True,
        "results": [{"keyword": "django", "sites": [{"site": "upwork", "jobs": jobs}]}],
        "errors": [],
    }


def _service(tmp_path: Path, scraper: FakeScraper) -> tuple[RunService, RunStore]:
    store = RunStore(tmp_path / "runs", keep_runs=50)
    return RunService(store, scraper), store


def test_run_finishes_and_saves_result(tmp_path: Path):
    async def scenario() -> RunStatus:
        scraper = FakeScraper({"ok": True, "results": [], "errors": []})
        service, store = _service(tmp_path, scraper)
        record = service.start(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait()
        return store.get(record.id).status

    assert asyncio.run(scenario()) is RunStatus.SUCCEEDED


def test_second_run_is_refused_while_first_is_active(tmp_path: Path):
    async def scenario() -> None:
        scraper = FakeScraper({"ok": True})
        service, _ = _service(tmp_path, scraper)
        service.start(("django",), ("upwork",), notify_discord=False)
        with pytest.raises(RunInProgressError):
            service.start(("flask",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait()

    asyncio.run(scenario())


def test_new_run_is_allowed_after_first_finishes(tmp_path: Path):
    async def scenario() -> int:
        scraper = FakeScraper({"ok": True})
        service, store = _service(tmp_path, scraper)
        scraper.release.set()
        service.start(("django",), ("upwork",), notify_discord=False)
        await service.wait()
        service.start(("flask",), ("upwork",), notify_discord=False)
        await service.wait()
        return len(store.list_recent())

    assert asyncio.run(scenario()) == 2


def test_mcp_failure_marks_run_failed(tmp_path: Path):
    async def scenario() -> str | None:
        scraper = FakeScraper(McpUnavailableError("MCP down"))
        service, store = _service(tmp_path, scraper)
        record = service.start(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait()
        return store.get(record.id).error

    assert asyncio.run(scenario()) == "MCP down"


def test_unexpected_failure_hides_detail(tmp_path: Path):
    async def scenario() -> str | None:
        scraper = FakeScraper(RuntimeError("secret detail"))
        service, store = _service(tmp_path, scraper)
        record = service.start(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait()
        return store.get(record.id).error

    assert asyncio.run(scenario()) == "The scrape failed."


def _notified_run(tmp_path: Path, scraper: FakeScraper):
    async def scenario():
        service, store = _service(tmp_path, scraper)
        record = service.start(("django",), ("upwork",), notify_discord=True)
        scraper.release.set()
        await service.wait()
        return store.get(record.id)

    return asyncio.run(scenario())


def test_run_without_notify_never_touches_discord(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(2))

    async def scenario():
        service, store = _service(tmp_path, scraper)
        record = service.start(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait()
        return store.get(record.id)

    record = asyncio.run(scenario())

    assert record.discord_status is None
    assert scraper.sent_messages == []


def test_notify_sends_all_jobs_to_default_channel_with_mention(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(2))
    scraper.send_outcomes = [_delivery(2, 0)]

    record = _notified_run(tmp_path, scraper)

    assert scraper.sent_messages == [
        (CHANNEL_ID, True, None, [{"title": "job 0"}, {"title": "job 1"}])
    ]
    assert record.status is RunStatus.SUCCEEDED
    assert record.discord_status is DiscordStatus.SENT
    assert (record.discord_sent, record.discord_failed, record.discord_error) == (2, 0, None)


def test_notify_without_mention_user_sends_without_mention(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = {**DISCORD_SETTINGS, "mention_user_id": None}

    _notified_run(tmp_path, scraper)

    assert scraper.sent_messages[0][1] is False


def test_notify_splits_jobs_in_chunks_of_fifty(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(120))
    scraper.send_outcomes = [_delivery(50, 0), _delivery(48, 2), _delivery(20, 0)]

    record = _notified_run(tmp_path, scraper)

    assert [len(message[3]) for message in scraper.sent_messages] == [50, 50, 20]
    assert (record.discord_sent, record.discord_failed) == (118, 2)
    assert record.discord_status is DiscordStatus.PARTIAL


def test_notify_counts_only_job_messages_not_the_summary(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(100))
    scraper.send_outcomes = [_delivery(50, 0), _delivery(50, 0)]

    record = _notified_run(tmp_path, scraper)

    assert (record.discord_sent, record.discord_failed) == (100, 0)
    assert record.discord_status is DiscordStatus.SENT


def test_notify_ignores_a_failed_summary_message(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(2))
    scraper.send_outcomes = [_delivery(2, 0, summary_status="failed")]

    record = _notified_run(tmp_path, scraper)

    assert (record.discord_sent, record.discord_failed) == (2, 0)
    assert record.discord_status is DiscordStatus.SENT


def test_notify_with_failed_text_message_is_failed(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(0))
    scraper.send_outcomes = [_text_delivery("failed")]

    record = _notified_run(tmp_path, scraper)

    assert (record.discord_sent, record.discord_failed) == (0, 1)
    assert record.discord_status is DiscordStatus.FAILED


def test_notify_mentions_only_on_the_first_chunk(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(120))

    _notified_run(tmp_path, scraper)

    assert [message[1] for message in scraper.sent_messages] == [True, False, False]


def test_notify_keeps_counts_when_a_later_chunk_raises(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(120))
    scraper.send_outcomes = [_delivery(50, 0), DiscordForbiddenError()]

    record = _notified_run(tmp_path, scraper)

    assert len(scraper.sent_messages) == 2
    assert record.discord_status is DiscordStatus.PARTIAL
    assert (record.discord_sent, record.discord_failed) == (50, 0)
    assert record.discord_error == DiscordForbiddenError.default_message


def test_notify_with_first_chunk_raising_is_failed(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(120))
    scraper.send_outcomes = [DiscordUnauthorizedError()]

    record = _notified_run(tmp_path, scraper)

    assert len(scraper.sent_messages) == 1
    assert record.discord_status is DiscordStatus.FAILED
    assert (record.discord_sent, record.discord_failed) == (0, 0)
    assert record.discord_error == DiscordUnauthorizedError.default_message


@pytest.mark.parametrize(
    "error",
    [
        DiscordNotConfiguredError(),
        DiscordUnauthorizedError(),
        DiscordForbiddenError(),
        ConfigInvalidError("text is too long"),
        McpUnavailableError("MCP down"),
    ],
)
def test_notify_maps_known_errors_to_their_message(tmp_path: Path, error: Exception):
    scraper = FakeScraper(_jobs_result(1))
    scraper.send_outcomes = [error]

    record = _notified_run(tmp_path, scraper)

    assert record.discord_error == str(error)


def test_notify_unknown_error_after_partial_keeps_generic_message(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(120))
    scraper.send_outcomes = [_delivery(50, 0), RuntimeError("secret detail")]

    record = _notified_run(tmp_path, scraper)

    assert record.discord_status is DiscordStatus.PARTIAL
    assert record.discord_error == "Sending to Discord failed."
    assert record.discord_sent == 50


def test_notify_text_with_long_keywords_fits_with_mention_prefix(tmp_path: Path):
    async def scenario() -> list[tuple]:
        scraper = FakeScraper(McpUnavailableError("MCP down"))
        service, _ = _service(tmp_path, scraper)
        service.start(("k" * 3000,), ("upwork",), notify_discord=True)
        scraper.release.set()
        await service.wait()
        return scraper.sent_messages

    text = asyncio.run(scenario())[0][2]

    assert len(f"<@{USER_ID}>\n{text}") <= 2000
    assert text.endswith(": MCP down")


def test_notify_text_without_overflow_is_unchanged(tmp_path: Path):
    scraper = FakeScraper(McpUnavailableError("MCP down"))

    _notified_run(tmp_path, scraper)

    assert scraper.sent_messages[0][2] == "Run failed for django on upwork: MCP down"


def test_notify_disk_error_on_sending_still_prunes(tmp_path: Path):
    async def scenario() -> int:
        scraper = FakeScraper(_jobs_result(1))
        service, store = _service(tmp_path, scraper)
        pruned: list[int] = []

        def broken_update(*arguments, **keywords):
            raise OSError("disk full")

        store.update_discord = broken_update
        store.prune = lambda: pruned.append(1)
        service.start(("django",), ("upwork",), notify_discord=True)
        scraper.release.set()
        await service.wait()
        return len(pruned)

    assert asyncio.run(scenario()) == 1


def test_notify_with_every_message_failed_is_failed(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(2))
    scraper.send_outcomes = [_delivery(0, 2)]

    record = _notified_run(tmp_path, scraper)

    assert record.discord_status is DiscordStatus.FAILED
    assert (record.discord_sent, record.discord_failed) == (0, 2)


def test_notify_with_zero_jobs_sends_one_text_message(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(0))

    record = _notified_run(tmp_path, scraper)

    assert scraper.sent_messages == [(CHANNEL_ID, True, "django on upwork found 0 jobs", None)]
    assert record.discord_status is DiscordStatus.SENT


def test_notify_after_failed_run_sends_failure_text(tmp_path: Path):
    scraper = FakeScraper(McpUnavailableError("MCP down"))

    record = _notified_run(tmp_path, scraper)

    assert scraper.sent_messages == [
        (CHANNEL_ID, True, "Run failed for django on upwork: MCP down", None)
    ]
    assert record.status is RunStatus.FAILED
    assert record.discord_status is DiscordStatus.SENT


def test_notify_after_unexpected_failure_hides_detail_in_text(tmp_path: Path):
    scraper = FakeScraper(RuntimeError("secret detail"))

    _notified_run(tmp_path, scraper)

    assert scraper.sent_messages[0][2] == "Run failed for django on upwork: The scrape failed."


def test_notify_without_token_fails_and_sends_nothing(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = {**DISCORD_SETTINGS, "configured": False}

    record = _notified_run(tmp_path, scraper)

    assert scraper.sent_messages == []
    assert record.discord_status is DiscordStatus.FAILED
    assert record.discord_error == "Discord token is not configured."
    assert record.status is RunStatus.SUCCEEDED


def test_notify_without_default_channel_fails_and_sends_nothing(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = {**DISCORD_SETTINGS, "default_channel_id": None}

    record = _notified_run(tmp_path, scraper)

    assert scraper.sent_messages == []
    assert record.discord_status is DiscordStatus.FAILED
    assert record.discord_error == "No default Discord channel is set."


def test_notify_send_error_hides_detail(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(1))
    scraper.send_outcomes = [RuntimeError("secret detail")]

    record = _notified_run(tmp_path, scraper)

    assert record.discord_status is DiscordStatus.FAILED
    assert record.discord_error == "Sending to Discord failed."
    assert record.status is RunStatus.SUCCEEDED


def test_notify_settings_error_marks_discord_failed(tmp_path: Path):
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = McpUnavailableError("MCP down")

    record = _notified_run(tmp_path, scraper)

    assert record.discord_status is DiscordStatus.FAILED
    assert record.discord_error == "Sending to Discord failed."


def test_run_stays_busy_while_discord_is_sending(tmp_path: Path):
    async def scenario() -> tuple[DiscordStatus | None, bool]:
        scraper = FakeScraper(_jobs_result(1))
        gate = asyncio.Event()
        original = scraper.send_discord_message

        async def slow_send(*arguments):
            await gate.wait()
            return await original(*arguments)

        scraper.send_discord_message = slow_send
        service, store = _service(tmp_path, scraper)
        record = service.start(("django",), ("upwork",), notify_discord=True)
        scraper.release.set()
        for _ in range(20):
            await asyncio.sleep(0)
        current = store.get(record.id)
        is_busy = False
        try:
            service.ensure_idle()
        except RunInProgressError:
            is_busy = True
        gate.set()
        await service.wait()
        return current.discord_status, is_busy

    assert asyncio.run(scenario()) == (DiscordStatus.SENDING, True)
