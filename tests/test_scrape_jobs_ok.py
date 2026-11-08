from __future__ import annotations

from unittest.mock import MagicMock, patch

from scraper.job_settings import SettingsMissingError
from scraper.types import JOB_FIELD_ORDER


def _make_config(keyword: str = "data analyst", site: str = "jobstreet"):
    cfg = MagicMock()
    cfg.keywords = (keyword,)
    cfg.enabled_site_names.return_value = (site,)
    cfg.output_dir = MagicMock()
    return cfg


@patch("mcp_server.server.mongo")
@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_raw_output")
@patch("mcp_server.server._read_site_output")
def test_ok_true_when_zero_jobs(mock_read, mock_read_raw, mock_load, mock_run, mock_mongo):
    """0 jobs returned but fetch succeeded → ok must be True."""
    mock_load.return_value = _make_config()
    mock_read_raw.return_value = None
    mock_read.return_value = {
        "keyword": "data analyst",
        "fields": ["title"],
        "count": 0,
        "jobs": [],
        "max_age_hours": 24,
        "filter": None,
    }

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["results"][0]["sites"][0]["count"] == 0


@patch("mcp_server.server.mongo")
@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_raw_output")
@patch("mcp_server.server._read_site_output")
def test_ok_true_when_jobs_found(mock_read, mock_read_raw, mock_load, mock_run, mock_mongo):
    """Jobs found → ok must be True."""
    mock_load.return_value = _make_config()
    mock_read_raw.return_value = None
    mock_read.return_value = {
        "keyword": "data analyst",
        "fields": ["title"],
        "count": 2,
        "jobs": [{"title": "A"}, {"title": "B"}],
        "max_age_hours": 24,
        "filter": None,
    }

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["results"][0]["sites"][0]["count"] == 2


@patch("mcp_server.server.mongo")
@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_raw_output")
@patch("mcp_server.server._read_site_output")
def test_ok_false_when_fetch_failed(mock_read, mock_read_raw, mock_load, mock_run, mock_mongo):
    """Fetch failed → ok must be False, error captured, sites list empty."""
    mock_load.return_value = _make_config()
    mock_read_raw.return_value = None
    mock_read.return_value = {
        "error": "fetch failed",
        "url": "https://example.com",
        "keyword": "data analyst",
    }

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is False
    assert len(result["errors"]) == 1
    assert result["errors"][0]["reason"] == "fetch failed"
    assert result["results"][0]["sites"] == []


@patch("mcp_server.server.mongo")
@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_raw_output")
@patch("mcp_server.server._read_site_output")
def test_ok_false_when_output_missing(mock_read, mock_read_raw, mock_load, mock_run, mock_mongo):
    """Missing output file (None from _read_site_output) → ok False."""
    mock_load.return_value = _make_config()
    mock_read_raw.return_value = None
    mock_read.return_value = None

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result["ok"] is False
    assert len(result["errors"]) == 1
    assert result["results"][0]["sites"] == []


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._write_status")
@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_raw_output")
@patch("mcp_server.server._read_site_output")
def test_scrape_jobs_writes_status(
    mock_read, mock_read_raw, mock_load, mock_run, mock_write_status, mock_mongo
):
    """scrape_jobs must call _write_status exactly once after a run."""
    mock_load.return_value = _make_config()
    mock_read_raw.return_value = None
    mock_read.return_value = {
        "keyword": "data analyst",
        "fields": ["title"],
        "count": 1,
        "jobs": [{"title": "A"}],
        "max_age_hours": None,
        "filter": None,
    }

    from mcp_server.server import scrape_jobs

    scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    mock_write_status.assert_called_once()
    result_arg, duration_arg = mock_write_status.call_args.args
    assert result_arg["ok"] is True
    assert isinstance(duration_arg, float)


@patch("mcp_server.server.mongo")
@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_raw_output")
@patch("mcp_server.server._read_site_output")
def test_scrape_jobs_normalizes_jobs_to_canonical_schema(
    mock_read, mock_read_raw, mock_load, mock_run, mock_mongo
):
    mock_load.return_value = _make_config()
    mock_read_raw.return_value = None
    mock_read.return_value = {
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
    }

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
@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_raw_output")
@patch("mcp_server.server._read_site_output")
def test_scrape_jobs_returns_mongo_id_and_builds_document(
    mock_read, mock_read_raw, mock_load, mock_run, mock_mongo
):
    """One document per run: raw_results (all jobs) + filtered_results (cut-down) + per_site_counts."""
    mock_load.return_value = _make_config()
    mock_read.return_value = {
        "keyword": "data analyst",
        "fields": ["title"],
        "count": 2,
        "jobs": [{"title": "A"}, {"title": "B"}],
        "max_age_hours": 24,
        "filter": None,
    }
    mock_read_raw.return_value = {
        "keyword": "data analyst",
        "fields": list(JOB_FIELD_ORDER),
        "count": 5,
        "jobs": [{"title": t} for t in "ABCDE"],
    }
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
@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_raw_output", return_value=None)
@patch("mcp_server.server._read_site_output")
def test_scrape_jobs_sets_note_on_error(mock_read, mock_read_raw, mock_load, mock_run, mock_mongo):
    mock_load.return_value = _make_config()
    mock_read.return_value = {
        "error": "fetch failed",
        "url": "https://x",
        "keyword": "data analyst",
    }
    mock_mongo.insert_run.return_value = "id1"

    from mcp_server.server import scrape_jobs

    scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])
    doc = mock_mongo.insert_run.call_args.args[0]
    assert doc["note"] is not None and "jobstreet" in doc["note"]


@patch("mcp_server.server.mongo")
@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_raw_output", return_value=None)
@patch("mcp_server.server._read_site_output")
def test_scrape_jobs_skips_mongo_when_save_run_is_false(
    mock_read, mock_read_raw, mock_load, mock_run, mock_mongo
):
    mock_load.return_value = _make_config()
    mock_read.return_value = {
        "keyword": "data analyst",
        "fields": ["title"],
        "count": 1,
        "jobs": [{"title": "A"}],
        "max_age_hours": 24,
        "filter": None,
    }

    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"], save_run=False)

    mock_mongo.insert_run.assert_not_called()
    assert result["mongo_id"] is None
    assert result["ok"] is True
    assert result["results"][0]["sites"][0]["count"] == 1


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


@patch("mcp_server.server._load_config", side_effect=SettingsMissingError("settings missing"))
def test_ok_false_when_settings_cannot_load(mock_load):
    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=["data analyst"], sites=["jobstreet"])

    assert result == {"ok": False, "error": "settings missing"}


RAW_PAYLOAD = {"keyword": "data analyst", "count": 3, "jobs": [{"title": "A"}, {"title": "B"}]}
FILTERED_PAYLOAD = {
    "keyword": "data analyst",
    "fields": ["title"],
    "count": 1,
    "jobs": [{"title": "A"}],
    "max_age_hours": None,
    "filter": None,
}


def _scrape(mock_read, mock_read_raw, mock_load, **kwargs):
    mock_load.return_value = _make_config()
    mock_read_raw.return_value = RAW_PAYLOAD
    mock_read.return_value = FILTERED_PAYLOAD

    from mcp_server.server import scrape_jobs

    return scrape_jobs(keywords=["data analyst"], sites=["jobstreet"], **kwargs)


@patch("mcp_server.server.mongo")
@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_raw_output")
@patch("mcp_server.server._read_site_output")
def test_scrape_jobs_omits_payloads_by_default(
    mock_read, mock_read_raw, mock_load, mock_run, mock_mongo
):
    result = _scrape(mock_read, mock_read_raw, mock_load)

    assert "raw_results" not in result
    assert "filtered_results" not in result


@patch("mcp_server.server.mongo")
@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_raw_output")
@patch("mcp_server.server._read_site_output")
def test_scrape_jobs_includes_raw_and_filtered_payloads_when_asked(
    mock_read, mock_read_raw, mock_load, mock_run, mock_mongo
):
    result = _scrape(mock_read, mock_read_raw, mock_load, include_payloads=True)

    assert result["raw_results"] == [
        {"keyword": "data analyst", "site": "jobstreet", "payload": RAW_PAYLOAD}
    ]
    assert result["filtered_results"] == [
        {"keyword": "data analyst", "site": "jobstreet", "payload": FILTERED_PAYLOAD}
    ]


@patch("mcp_server.server.mongo")
@patch("mcp_server.server.run_scraper", return_value=0)
@patch("mcp_server.server._load_config")
@patch("mcp_server.server._read_site_raw_output")
@patch("mcp_server.server._read_site_output")
def test_scrape_jobs_includes_payloads_when_run_is_not_saved(
    mock_read, mock_read_raw, mock_load, mock_run, mock_mongo
):
    result = _scrape(mock_read, mock_read_raw, mock_load, include_payloads=True, save_run=False)

    assert result["mongo_id"] is None
    assert len(result["raw_results"]) == 1
    assert len(result["filtered_results"]) == 1
