from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from scraper.api.client import ApiError
from scraper.api.registry import API_SOURCES
from scraper.api.upwork import UpworkApi
from scraper.config_loader import ApiConfig
from scraper.runner import _can_call_api, run_one
from scraper.sites import SCRAPERS
from scraper.sites.upwork import UpworkScraper
from scraper.types import Job, empty_job

FIELDS = frozenset({"site", "matched_keyword", "title", "company", "url", "requirements"})
URL = "https://www.upwork.com/nx/search/jobs/?q=python"


def _scraper() -> UpworkScraper:
    return UpworkScraper(url=URL, limit=30)


def _run(tmp_path: Path, fetcher: MagicMock, api_search, api_detail=None) -> None:
    run_one(
        _scraper(),
        fetcher,
        tmp_path,
        "python",
        FIELDS,
        None,
        {},
        api_search=api_search,
        api_detail=api_detail,
    )


def _job() -> Job:
    job = empty_job("upwork", "Role", "Upwork Client")
    job["url"] = "https://www.upwork.com/jobs/~1"
    return job


def test_upwork_is_registered():
    assert SCRAPERS["upwork"] is UpworkScraper
    assert API_SOURCES["upwork"] is UpworkApi


def test_scraper_is_api_only_and_parses_nothing():
    assert _scraper().api_only is True
    assert _scraper().parse("<html></html>") == []


def test_api_error_writes_an_error_and_never_fetches_html(tmp_path: Path):
    fetcher = MagicMock()

    def _fail():
        raise ApiError("http_403", "blocked")

    _run(tmp_path, fetcher, _fail)

    payload = json.loads((tmp_path / "upwork.json").read_text())
    assert payload["error"] == "api failed: http_403"
    assert payload["source"] == "api"
    assert "blocked" not in json.dumps(payload)
    raw = json.loads((tmp_path / "upwork.raw.json").read_text())
    assert raw["count"] == 0
    fetcher.fetch.assert_not_called()


def test_unexpected_exception_writes_an_error_and_never_fetches_html(tmp_path: Path):
    fetcher = MagicMock()

    def _crash():
        raise KeyError("shape")

    _run(tmp_path, fetcher, _crash)

    payload = json.loads((tmp_path / "upwork.json").read_text())
    assert payload["error"] == "api failed: unexpected_error:KeyError"
    fetcher.fetch.assert_not_called()


def test_missing_api_search_writes_an_error_and_never_fetches_html(tmp_path: Path):
    fetcher = MagicMock()

    _run(tmp_path, fetcher, None)

    payload = json.loads((tmp_path / "upwork.json").read_text())
    assert payload["error"] == "api failed: api_disabled"
    fetcher.fetch.assert_not_called()


def test_blank_requirements_never_fetch_the_job_page(tmp_path: Path):
    fetcher = MagicMock()

    _run(tmp_path, fetcher, lambda: [_job()], lambda _job: None)

    payload = json.loads((tmp_path / "upwork.json").read_text())
    assert payload["count"] == 1
    fetcher.fetch.assert_not_called()


def test_zero_results_is_not_an_error(tmp_path: Path):
    _run(tmp_path, MagicMock(), lambda: [])

    payload = json.loads((tmp_path / "upwork.json").read_text())
    assert "error" not in payload
    assert payload["count"] == 0


def test_api_only_site_without_locations_cannot_call_the_api():
    empty = ApiConfig(enabled=True, locations=(), country_wide=False)
    remote = ApiConfig(enabled=True, locations=("Remote",), country_wide=False)

    assert _can_call_api(_scraper(), empty, "upwork") is False
    assert _can_call_api(_scraper(), remote, "upwork") is True


def test_html_site_without_locations_still_uses_the_api_path():
    scraper = MagicMock()
    scraper.api_only = False
    empty = ApiConfig(enabled=True, locations=(), country_wide=False)

    assert _can_call_api(scraper, empty, "glints") is True
