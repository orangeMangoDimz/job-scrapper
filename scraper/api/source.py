from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from ..types import Job

COUNTRY_LABELS: frozenset[str] = frozenset({"indonesia"})


class ApiSource(Protocol):
    name: str
    # value passed as `location` for the country-wide call (None = no location param)
    country_location: str | None

    def search(
        self, keyword: str, location: str | None, max_age_hours: int | None, limit: int
    ) -> list[Job]: ...

    def detail(self, job: Job) -> str | None: ...


def is_country_level(job: Job) -> bool:
    return (job.get("location") or "").strip().lower() in COUNTRY_LABELS


def _dedup_key(job: Job) -> tuple[str, ...]:
    if job.get("job_id"):
        return ("id", str(job["job_id"]))
    if job.get("url"):
        return ("url", str(job["url"]))
    return ("tc", job["title"], job["company"])


def dedup_jobs(jobs: Iterable[Job]) -> list[Job]:
    seen: set[tuple[str, ...]] = set()
    unique: list[Job] = []
    for job in jobs:
        key = _dedup_key(job)
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique


def search_all(
    source: ApiSource,
    keyword: str,
    locations: Iterable[str],
    country_wide: bool,
    max_age_hours: int | None,
    limit: int,
) -> list[Job]:
    """One call per city, plus an optional country-wide call kept to 'Indonesia'-only jobs.

    ApiError is not caught: the runner falls back to HTML for the whole site+keyword.
    """
    jobs: list[Job] = []
    for location in locations:
        jobs.extend(source.search(keyword, location, max_age_hours, limit))
    if country_wide:
        country_jobs = source.search(keyword, source.country_location, max_age_hours, limit)
        jobs.extend(job for job in country_jobs if is_country_level(job))
    return dedup_jobs(jobs)
