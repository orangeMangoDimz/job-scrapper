from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scraper.dedup import dedup_key
from scraper.runner import run_one
from scraper.sites._pagination import with_query_param
from scraper.sites.base import Scraper

_FIELDS = frozenset({"title", "company", "url"})


class StubFetcher:
    """Records fetched URLs; returns non-empty html for every page."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def fetch(self, url: str):
        self.urls.append(url)
        return SimpleNamespace(html="<html>ok</html>", attempts=[])


class StubScraper(Scraper):
    """Paginating scraper that yields a pre-canned list of jobs per page."""

    name = "jobstreet"
    requires_search_html = True

    def __init__(self, pages: list[list[dict]], limit: int, max_pages: int) -> None:
        super().__init__(url="https://id.jobstreet.com/id/x", limit=limit, max_pages=max_pages)
        self._pages = pages
        self._i = 0

    def parse(self, html: str) -> list[dict]:  # type: ignore[override]
        page = self._pages[self._i] if self._i < len(self._pages) else []
        self._i += 1
        return [dict(j) for j in page]

    def page_url(self, page: int) -> str | None:
        if page == 0:
            return self.url
        return with_query_param(self.url, "page", str(page + 1))


class FakeSeen:
    def __init__(self, seeded=()) -> None:
        self.persisted: set[str] = set(seeded)
        self.in_run: set[str] = set()
        self.marked: list[dict] = []

    def is_seen(self, key: str) -> bool:
        return key in self.persisted or key in self.in_run

    def remember_in_run(self, key: str) -> None:
        self.in_run.add(key)

    def mark_seen(self, records: list[dict]) -> None:
        self.marked.extend(records)
        self.persisted.update(r["dedup_key"] for r in records)


def _job(title: str) -> dict:
    return {
        "site": "jobstreet",
        "title": title,
        "company": "ACME",
        "url": f"https://id.jobstreet.com/id/job/{title}",
    }


def _run(scraper, seen, tmp_path: Path, fetcher=None, max_age_hours=None):
    fetcher = fetcher or StubFetcher()
    run_one(
        scraper,
        fetcher,
        tmp_path,
        "software engineer",
        _FIELDS,
        max_age_hours,
        {},
        seen=seen,
        max_pages=scraper.max_pages,
        page_delay_sec=0.0,
    )
    out = json.loads((tmp_path / "jobstreet.json").read_text())
    raw = json.loads((tmp_path / "jobstreet.raw.json").read_text())
    return out, raw, fetcher


def test_already_seen_jobs_are_dropped(tmp_path: Path):
    seen = FakeSeen(seeded={dedup_key(_job("A"))})
    scraper = StubScraper([[_job("A"), _job("B")]], limit=5, max_pages=3)
    out, raw, _ = _run(scraper, seen, tmp_path)

    assert {j["title"] for j in out["jobs"]} == {"B"}  # A already seen
    assert {j["title"] for j in raw["jobs"]} == {"A", "B"}  # raw keeps everything parsed


def test_paginates_until_quota_when_first_page_all_seen(tmp_path: Path):
    seen = FakeSeen(seeded={dedup_key(_job("A")), dedup_key(_job("B"))})
    scraper = StubScraper([[_job("A"), _job("B")], [_job("C"), _job("D")]], limit=2, max_pages=3)
    out, _, fetcher = _run(scraper, seen, tmp_path)

    assert {j["title"] for j in out["jobs"]} == {"C", "D"}  # advanced to page 1
    assert len(fetcher.urls) == 2  # fetched page 0 then page 1
    assert {r["dedup_key"] for r in seen.marked} == {dedup_key(_job("C")), dedup_key(_job("D"))}


def test_quota_met_on_first_page_skips_further_fetches(tmp_path: Path):
    seen = FakeSeen()
    scraper = StubScraper([[_job("A"), _job("B"), _job("C")]], limit=2, max_pages=5)
    out, _, fetcher = _run(scraper, seen, tmp_path)

    assert {j["title"] for j in out["jobs"]} == {"A", "B"}
    assert len(fetcher.urls) == 1  # never fetched page 1


def test_repeat_page_stops_pagination(tmp_path: Path):
    # Site ignores the page param and re-serves page 0 → must stop, not loop forever.
    same = [_job("A"), _job("B")]
    seen = FakeSeen()
    scraper = StubScraper([same, same, same], limit=5, max_pages=5)
    out, _, fetcher = _run(scraper, seen, tmp_path)

    assert {j["title"] for j in out["jobs"]} == {"A", "B"}
    assert len(fetcher.urls) == 2  # page 0, then page 1 detected as a repeat → stop
