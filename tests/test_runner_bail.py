from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from scraper.runner import run_one


def _make_fetcher(html: str | None):
    fetcher = MagicMock()
    result = MagicMock()
    result.html = html
    result.attempts = ()
    fetcher.fetch.return_value = result
    return fetcher


def test_run_one_bails_when_html_required_and_missing(tmp_path: Path):
    scraper = MagicMock()
    scraper.name = "glints"
    scraper.url = "https://glints.com/x"
    scraper.requires_search_html = True
    scraper.parse = MagicMock(return_value=[])
    fetcher = _make_fetcher(html=None)

    run_one(
        scraper=scraper,
        fetcher=fetcher,
        output_dir=tmp_path,
        keyword="data analyst",
        fields=frozenset({"title"}),
        max_age_hours=None,
        content_filter={},
    )

    out = json.loads((tmp_path / "glints.json").read_text())
    assert out == {
        "error": "fetch failed",
        "url": "https://glints.com/x",
        "keyword": "data analyst",
        "attempts": [],
    }
    scraper.parse.assert_not_called()


def test_run_one_skips_bail_for_indeed_style_scraper(tmp_path: Path):
    scraper = MagicMock()
    scraper.name = "indeed"
    scraper.url = "https://id.indeed.com/jobs?q=x"
    scraper.requires_search_html = False
    scraper.limit = 10
    fake_job = {
        "site": "indeed",
        "matched_keyword": "data analyst",
        "title": "API job",
        "company": "ACME",
        "url": "https://id.indeed.com/viewjob?jk=1",
        "requirements": "from API",
        "posted_at": None,
        "posted_date": None,
    }
    scraper.collect = MagicMock(return_value=[fake_job])
    fetcher = _make_fetcher(html=None)

    run_one(
        scraper=scraper,
        fetcher=fetcher,
        output_dir=tmp_path,
        keyword="data analyst",
        fields=frozenset({"title", "url", "requirements"}),
        max_age_hours=None,
        content_filter={},
    )

    scraper.collect.assert_called_once_with("")
    out = json.loads((tmp_path / "indeed.json").read_text())
    assert out["count"] == 1
    assert out["jobs"][0]["title"] == "API job"
    assert out["jobs"][0]["requirements"] == "from API"
