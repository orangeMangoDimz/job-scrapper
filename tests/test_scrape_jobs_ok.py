from __future__ import annotations

from unittest.mock import MagicMock, patch

from scraper.runner import SiteRunResult
from scraper.types import JOB_FIELD_ORDER


def _make_config(keyword: str = "data analyst", site: str = "jobstreet"):
    cfg = MagicMock()
    cfg.keywords = (keyword,)
    cfg.enabled_site_names.return_value = (site,)
    return cfg


def _result(keyword, site, filtered, raw=None):
    return SiteRunResult(
        keyword=keyword,
        site=site,
        filtered=filtered,
        raw=raw if raw is not None else {"keyword": keyword, "fields": [], "count": 0, "jobs": []},
    )


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_ok_true_when_zero_jobs(mock_run, mock_load, mock_mongo):
    """0 jobs returned but fetch succeeded → ok must be True."""
    mock_load.return_value = _make_config()
    mock_run.return_value = (
        0,
        [
            _result(
                "data analyst",
                "jobstreet",
                {
                    "keyword": "data analyst",
                    "fields": ["title"],
                    "count": 0,
                    "jobs": [],
                    "max_age_hours": 24,
                    "filter": None,
                },
            )
        ],
    )

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["results"][0]["sites"][0]["count"] == 0


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_ok_true_when_jobs_found(mock_run, mock_load, mock_mongo):
    """Jobs found → ok must be True."""
    mock_load.return_value = _make_config()
    mock_run.return_value = (
        0,
        [
            _result(
                "data analyst",
                "jobstreet",
                {
                    "keyword": "data analyst",
                    "fields": ["title"],
                    "count": 2,
                    "jobs": [{"title": "A"}, {"title": "B"}],
                    "max_age_hours": 24,
                    "filter": None,
                },
            )
        ],
    )

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["results"][0]["sites"][0]["count"] == 2


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_ok_false_when_fetch_failed(mock_run, mock_load, mock_mongo):
    """Fetch failed → ok must be False, error captured, sites list empty."""
    mock_load.return_value = _make_config()
    mock_run.return_value = (
        0,
        [
            _result(
                "data analyst",
                "jobstreet",
                {
                    "error": "fetch failed",
                    "url": "https://example.com",
                    "keyword": "data analyst",
                },
            )
        ],
    )

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is False
    assert len(result["errors"]) == 1
    assert result["errors"][0]["reason"] == "fetch failed"
    assert result["results"][0]["sites"] == []


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_ok_false_when_site_result_missing(mock_run, mock_load, mock_mongo):
    """A requested (keyword, site) with no result from the scraper → ok False."""
    mock_load.return_value = _make_config()
    mock_run.return_value = (0, [])  # nothing came back for the requested pair

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is False
    assert len(result["errors"]) == 1
    assert result["results"][0]["sites"] == []


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._write_status")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_scrape_jobs_writes_status(mock_run, mock_load, mock_write_status, mock_mongo):
    """scrape_jobs must call _write_status exactly once after a run."""
    mock_load.return_value = _make_config()
    mock_run.return_value = (
        0,
        [
            _result(
                "data analyst",
                "jobstreet",
                {
                    "keyword": "data analyst",
                    "fields": ["title"],
                    "count": 1,
                    "jobs": [{"title": "A"}],
                    "max_age_hours": None,
                    "filter": None,
                },
            )
        ],
    )

    from mcp_server.server import scrape_jobs

    scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    mock_write_status.assert_called_once()
    result_arg, duration_arg = mock_write_status.call_args.args
    assert result_arg["ok"] is True
    assert isinstance(duration_arg, float)


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_scrape_jobs_normalizes_jobs_to_canonical_schema(mock_run, mock_load, mock_mongo):
    mock_load.return_value = _make_config()
    mock_run.return_value = (
        0,
        [
            _result(
                "data analyst",
                "jobstreet",
                {
                    "keyword": "data analyst",
                    "fields": ["title", "company", "url"],
                    "count": 1,
                    "jobs": [
                        {
                            "title": "Data Analyst",
                            "company": "ACME",
                            "url": "https://example.com/job/1",
                            "extra": "drop-me",
                        }
                    ],
                    "max_age_hours": 24,
                    "filter": None,
                },
            )
        ],
    )

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])
    site_entry = result["results"][0]["sites"][0]
    job = site_entry["jobs"][0]

    assert set(job.keys()) == set(JOB_FIELD_ORDER)
    assert job["site"] == "jobstreet"
    assert job["matched_keyword"] == "data analyst"
    assert "extra" not in job
    assert site_entry["count"] == 1


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_scrape_jobs_returns_mongo_id_and_builds_document(mock_run, mock_load, mock_mongo):
    """One document per run: raw_results (all jobs) + filtered_results (cut-down) + per_site_counts."""
    mock_load.return_value = _make_config()
    mock_run.return_value = (
        0,
        [
            _result(
                "data analyst",
                "jobstreet",
                filtered={
                    "keyword": "data analyst",
                    "fields": ["title"],
                    "count": 2,
                    "jobs": [{"title": "A"}, {"title": "B"}],
                    "max_age_hours": 24,
                    "filter": None,
                },
                raw={
                    "keyword": "data analyst",
                    "fields": list(JOB_FIELD_ORDER),
                    "count": 5,
                    "jobs": [{"title": t} for t in "ABCDE"],
                },
            )
        ],
    )
    mock_mongo.insert_run.return_value = "deadbeef"

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["mongo_id"] == "deadbeef"
    doc = mock_mongo.insert_run.call_args.args[0]
    assert doc["raw_results"][0]["payload"]["count"] == 5  # all jobs
    assert doc["filtered_results"][0]["payload"]["count"] == 2  # cut-down list
    assert doc["run_metadata"]["per_site_counts"] == {"jobstreet": {"data analyst": 2}}
    assert "raw_results" not in doc["run_metadata"]  # not nested
    assert doc["note"] is None  # no errors → no note


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._load_config")
@patch("mcp_server.server.run_scraper")
def test_scrape_jobs_sets_note_on_error(mock_run, mock_load, mock_mongo):
    mock_load.return_value = _make_config()
    mock_run.return_value = (
        0,
        [
            _result(
                "data analyst",
                "jobstreet",
                {"error": "fetch failed", "url": "https://x", "keyword": "data analyst"},
            )
        ],
    )
    mock_mongo.insert_run.return_value = "id1"

    from mcp_server.server import scrape_jobs

    scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])
    doc = mock_mongo.insert_run.call_args.args[0]
    assert doc["note"] is not None and "jobstreet" in doc["note"]


def test_get_scrape_response_structure_exposes_canonical_fields():
    from mcp_server.server import get_scrape_response_structure

    out = get_scrape_response_structure()

    assert out["tool"] == "scrape_jobs"
    assert out["job_fields"] == list(JOB_FIELD_ORDER)
    assert out["top_level_fields"] == [
        "ok",
        "keywords",
        "requested_sites",
        "exit_code",
        "results",
        "errors",
        "mongo_id",
    ]
