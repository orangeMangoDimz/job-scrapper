from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from mcp_server.discord_settings import StoredDiscordSettings

MAX_JOBS = 50
TEXT_LIMIT = 2000
ELLIPSIS = "…"
PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_]\w*)\}")

MessageKind = Literal["text", "job", "summary"]


class MessageInvalidError(ValueError):
    pass


@dataclass(frozen=True)
class OutgoingMessage:
    kind: MessageKind
    title: str | None
    content: str
    mention_user_id: str | None = None


def render_job(template: str, job: Mapping[str, Any]) -> str:
    def fill(match: re.Match[str]) -> str:
        value = job.get(match.group(1))
        return "" if value is None else str(value)

    return PLACEHOLDER_PATTERN.sub(fill, template)


def truncate(content: str, limit: int) -> str:
    if len(content) <= limit:
        return content
    if limit <= 0:
        return ""
    return content[: limit - len(ELLIPSIS)] + ELLIPSIS


def summary_text(count: int) -> str:
    return f"Total: {count} job(s)"


def _mention_target(settings: StoredDiscordSettings, mention: bool) -> str | None:
    return settings.mention_user_id if mention and settings.mention_user_id else None


def _mention_prefix(mention_user_id: str | None) -> str:
    return f"<@{mention_user_id}>\n" if mention_user_id else ""


def _build_text(mention_user_id: str | None, text: Any) -> tuple[OutgoingMessage, ...]:
    if not isinstance(text, str) or not text.strip():
        raise MessageInvalidError("text must not be empty")
    content = _mention_prefix(mention_user_id) + text
    if len(content) > TEXT_LIMIT:
        raise MessageInvalidError(
            f"text is {len(content)} characters with the mention, the limit is {TEXT_LIMIT}"
        )
    return (
        OutgoingMessage(kind="text", title=None, content=content, mention_user_id=mention_user_id),
    )


def _job_title(job: Mapping[str, Any]) -> str | None:
    title = job.get("title")
    return str(title) if title else None


def _job_content(prefix: str, body: str, max_chars: int) -> str:
    return truncate(prefix + truncate(body, max_chars - len(prefix)), TEXT_LIMIT)


def _build_jobs(
    settings: StoredDiscordSettings, mention_user_id: str | None, jobs: list[dict[str, Any]]
) -> tuple[OutgoingMessage, ...]:
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= MAX_JOBS:
        raise MessageInvalidError(f"jobs must hold 1 to {MAX_JOBS} jobs")
    if not all(isinstance(job, dict) for job in jobs):
        raise MessageInvalidError("every job must be a mapping")
    mention_ids = [mention_user_id, *[None] * (len(jobs) - 1)]
    messages = tuple(
        OutgoingMessage(
            kind="job",
            title=_job_title(job),
            content=_job_content(
                _mention_prefix(job_mention_id),
                render_job(settings.message_template, job),
                settings.max_chars,
            ),
            mention_user_id=job_mention_id,
        )
        for job, job_mention_id in zip(jobs, mention_ids, strict=True)
    )
    summary = OutgoingMessage(kind="summary", title=None, content=summary_text(len(jobs)))
    return (*messages, summary)


def build_messages(
    settings: StoredDiscordSettings,
    mention: bool,
    text: str | None,
    jobs: list[dict[str, Any]] | None,
) -> tuple[OutgoingMessage, ...]:
    if (text is None) == (jobs is None):
        raise MessageInvalidError("give exactly one of text or jobs")
    mention_user_id = _mention_target(settings, mention)
    if jobs is not None:
        return _build_jobs(settings, mention_user_id, jobs)
    return _build_text(mention_user_id, text)
