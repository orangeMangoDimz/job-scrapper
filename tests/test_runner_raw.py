from __future__ import annotations

from unittest.mock import MagicMock

from scraper import runner


def _job(title: str, location: str) -> dict:
    return {"title": title, "company": "ACME", "url": f"https://x/{title}", "location": location}


def test_run_one_returns_raw_before_filter():
    """raw holds ALL parsed jobs; filtered is cut down by filter + limit."""
    scraper = MagicMock()
    scraper.name = "fake"
    scraper.url = "https://example.test/search"
    scraper.limit = 5
    scraper.requires_search_html = True
    # 3 parsed jobs: 2 in jakarta, 1 in surabaya
    scraper.parse.return_value = [
        _job("A", "Jakarta"),
        _job("B", "Jakarta"),
        _job("C", "Surabaya"),
    ]

    fetcher = MagicMock()
    fetcher.fetch.return_value.html = "<html>ok</html>"
    fetcher.fetch.return_value.attempts = []

    result = runner.run_one(
        scraper,
        fetcher,
        "data analyst",
        frozenset({"title", "company", "url", "location"}),
        None,  # max_age_hours
        {"location": ["jakarta"]},  # content_filter drops Surabaya
    )

    assert result.keyword == "data analyst"
    assert result.site == "fake"
    assert result.raw["count"] == 3  # all parsed jobs survive
    assert {j["title"] for j in result.raw["jobs"]} == {"A", "B", "C"}
    assert result.filtered["count"] == 2  # Surabaya filtered out
    assert {j["title"] for j in result.filtered["jobs"]} == {"A", "B"}


def test_run_one_returns_reset_raw_on_fetch_failure():
    """A fetch failure yields an error-marked ``filtered`` + empty ``raw``.

    In-memory results can't carry across runs, so the file-staleness class the
    old disk-based code guarded against (output/ was a persistent volume) no
    longer exists.
    """
    scraper = MagicMock()
    scraper.name = "fake"
    scraper.url = "https://example.test/search"
    scraper.limit = 5
    scraper.requires_search_html = True
    scraper.parse.return_value = [_job("A", "Jakarta")]

    fetcher = MagicMock()
    fetcher.fetch.return_value.html = ""  # fetch failure
    fetcher.fetch.return_value.attempts = []

    result = runner.run_one(
        scraper,
        fetcher,
        "data analyst",
        frozenset({"title", "company", "url", "location"}),
        None,
        {},
    )

    assert result.filtered == {
        "error": "fetch failed",
        "url": "https://example.test/search",
        "keyword": "data analyst",
        "attempts": [],
    }
    assert result.raw == {
        "keyword": "data analyst",
        "count": 0,
        "jobs": [],
        "error": "fetch failed",
    }
    scraper.parse.assert_not_called()
