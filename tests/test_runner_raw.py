from __future__ import annotations

import json
from unittest.mock import MagicMock

from scraper import runner


def _job(title: str, location: str) -> dict:
    return {"title": title, "company": "ACME", "url": f"https://x/{title}", "location": location}


def test_run_one_writes_raw_before_filter(tmp_path):
    """raw.json holds ALL parsed jobs; the filtered json is cut down by filter+limit."""
    scraper = MagicMock()
    scraper.name = "fake"
    scraper.url = "https://example.test/search"
    scraper.limit = 5
    scraper.requires_search_html = True
    # 3 parsed jobs: 2 in jakarta, 1 in surabaya
    scraper.collect.return_value = [
        _job("A", "Jakarta"),
        _job("B", "Jakarta"),
        _job("C", "Surabaya"),
    ]

    fetcher = MagicMock()
    fetcher.fetch.return_value.html = "<html>ok</html>"
    fetcher.fetch.return_value.attempts = []

    runner.run_one(
        scraper,
        fetcher,
        tmp_path,
        "data analyst",
        frozenset({"title", "company", "url", "location"}),
        None,  # max_age_hours
        {"location": ["jakarta"]},  # content_filter drops Surabaya
    )

    raw = json.loads((tmp_path / "fake.raw.json").read_text())
    filtered = json.loads((tmp_path / "fake.json").read_text())

    assert raw["count"] == 3  # all parsed jobs survive
    assert {j["title"] for j in raw["jobs"]} == {"A", "B", "C"}
    assert filtered["count"] == 2  # Surabaya filtered out
    assert {j["title"] for j in filtered["jobs"]} == {"A", "B"}


def test_run_one_resets_raw_on_fetch_failure(tmp_path):
    """A later fetch failure must not leave the previous run's raw file on disk.

    output/ is a persistent volume; if the raw file is only written on success, a
    failed run would mis-attribute the previous run's jobs as its own raw_results.
    """
    scraper = MagicMock()
    scraper.name = "fake"
    scraper.url = "https://example.test/search"
    scraper.limit = 5
    scraper.requires_search_html = True
    scraper.collect.return_value = [_job("A", "Jakarta"), _job("B", "Jakarta")]

    fetcher = MagicMock()
    fetcher.fetch.return_value.attempts = []
    fields = frozenset({"title", "company", "url", "location"})

    # run 1: success → writes raw with 2 jobs
    fetcher.fetch.return_value.html = "<html>ok</html>"
    runner.run_one(scraper, fetcher, tmp_path, "data analyst", fields, None, {})
    assert json.loads((tmp_path / "fake.raw.json").read_text())["count"] == 2

    # run 2: fetch failure (no html) → raw must be reset, not stale
    fetcher.fetch.return_value.html = ""
    runner.run_one(scraper, fetcher, tmp_path, "data analyst", fields, None, {})

    raw = json.loads((tmp_path / "fake.raw.json").read_text())
    assert raw["count"] == 0
    assert raw["jobs"] == []
    assert raw.get("error") == "fetch failed"
