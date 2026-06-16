# scraper/fetchers/base.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..config import CHALLENGE_MARKERS
from ..log import get_logger

_LOG = get_logger()

_TITLE_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE)
_CHALLENGE_TITLES = (
    "just a moment",
    "attention required",
    "access denied",
    "security check",
    "verify you are human",
    "checking your browser",
)


def detect_challenge(html: str) -> str | None:
    match = _TITLE_RE.search(html)
    if match:
        title = match.group(1).strip()
        lowered = title.lower()
        for marker in _CHALLENGE_TITLES:
            if marker in lowered:
                return f"title={title}"
    if len(html) < 4096:
        for marker in CHALLENGE_MARKERS:
            if marker in html:
                return f"marker={marker}"
    return None


def looks_like_challenge(html: str) -> bool:
    return detect_challenge(html) is not None


@dataclass(frozen=True)
class FetchAttempt:
    fetcher: str
    code: str
    detail: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"fetcher": self.fetcher, "code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class FetchResult:
    html: str | None
    attempts: tuple[FetchAttempt, ...]


@runtime_checkable
class Fetcher(Protocol):
    name: str

    def fetch(self, url: str) -> tuple[str | None, FetchAttempt]: ...


class FetchChain:
    def __init__(self, fetchers: list[Fetcher]) -> None:
        self._fetchers = fetchers

    def fetch(self, url: str) -> FetchResult:
        attempts: list[FetchAttempt] = []
        for fetcher in self._fetchers:
            _LOG.debug("[fetch] trying {} for {}", fetcher.name, url)
            html, attempt = fetcher.fetch(url)
            attempts.append(attempt)
            if html and attempt.code == "ok":
                return FetchResult(html=html, attempts=tuple(attempts))
            _LOG.debug(
                "[fetch] {} insufficient ({}), falling through",
                fetcher.name,
                attempt.code,
            )
        return FetchResult(html=None, attempts=tuple(attempts))
