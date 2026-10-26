from __future__ import annotations

import pytest

from scraper.api.client import ApiError
from scraper.api.source import dedup_jobs, is_country_level, search_all
from scraper.types import Job, empty_job


def _job(job_id: str | None, location: str, url: str | None = None) -> Job:
    job = empty_job("jobstreet", f"T{job_id}", "C")
    job["job_id"] = job_id
    job["url"] = url
    job["location"] = location
    return job


class StubSource:
    name = "stub"
    country_location = "COUNTRY"

    def __init__(self, by_location: dict[str | None, list[Job] | Exception]) -> None:
        self.by_location = by_location
        self.calls: list[tuple[str, str | None, int | None, int]] = []

    def search(self, keyword: str, location: str | None, max_age_hours: int | None, limit: int):
        self.calls.append((keyword, location, max_age_hours, limit))
        result = self.by_location[location]
        if isinstance(result, Exception):
            raise result
        return list(result)

    def detail(self, job: Job) -> str | None:
        return None


def test_one_call_per_city_then_dedup():
    source = StubSource(
        {"A": [_job("1", "Jakarta"), _job("2", "Jakarta")], "B": [_job("2", "Jakarta")]}
    )
    jobs = search_all(source, "devops", ("A", "B"), country_wide=False, max_age_hours=72, limit=30)
    assert [j["job_id"] for j in jobs] == ["1", "2"]
    assert source.calls == [("devops", "A", 72, 30), ("devops", "B", 72, 30)]


def test_country_call_keeps_only_country_level_jobs():
    source = StubSource(
        {"A": [_job("1", "Jakarta")], "COUNTRY": [_job("9", "Indonesia"), _job("8", "Bali")]}
    )
    jobs = search_all(source, "devops", ("A",), country_wide=True, max_age_hours=None, limit=30)
    assert [j["job_id"] for j in jobs] == ["1", "9"]


def test_api_error_propagates_for_site_level_fallback():
    source = StubSource({"A": [_job("1", "Jakarta")], "B": ApiError("http_500")})
    with pytest.raises(ApiError):
        search_all(source, "devops", ("A", "B"), country_wide=False, max_age_hours=None, limit=30)


def test_dedup_falls_back_to_url_then_title_company():
    a = _job(None, "Jakarta", url="https://x/1")
    b = _job(None, "Jakarta", url="https://x/1")
    c = _job(None, "Jakarta")
    d = _job(None, "Jakarta")
    assert dedup_jobs([a, b, c, d]) == [a, c]


def test_is_country_level():
    assert is_country_level(_job("1", " Indonesia "))
    assert not is_country_level(_job("1", "Jakarta, Indonesia"))
