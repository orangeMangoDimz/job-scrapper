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
    line = "using proxy: socks5://user:secret@host:1080"  # pragma: allowlist secret

    assert redact(line) == "using proxy: socks5://***@host:1080"
