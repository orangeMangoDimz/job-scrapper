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
        for raw_line in lines:
            yield raw_line.decode("utf-8", "replace")
            last_sent = time.monotonic()
        if time.monotonic() - last_sent >= HEARTBEAT_SECONDS:
            yield None
            last_sent = time.monotonic()
        await asyncio.sleep(poll_seconds)
