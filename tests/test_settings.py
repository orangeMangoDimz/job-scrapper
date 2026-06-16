# tests/test_settings.py
from __future__ import annotations

import importlib


def _reload(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import scraper.settings as settings_mod

    return importlib.reload(settings_mod)


def test_defaults(monkeypatch):
    for k in (
        "MONGO_URI",
        "MONGO_DB_NAME",
        "MONGO_COLLECTION_NAME",
        "MONGO_SERVER_SELECTION_TIMEOUT_MS",
        "LOG_LEVEL",
        "LOG_FORMAT",
        "LOG_FILE",
    ):
        monkeypatch.delenv(k, raising=False)
    s = _reload(monkeypatch)
    assert s.MONGO_URI == "mongodb://localhost:27017"
    assert s.MONGO_DB_NAME == "job_scraper"
    assert s.MONGO_COLLECTION_NAME == "scrape_runs"
    assert s.MONGO_SERVER_SELECTION_TIMEOUT_MS == 3000
    assert s.LOG_LEVEL == "INFO"
    assert s.LOG_FORMAT == "json"
    assert s.LOG_FILE == ""


def test_env_overrides(monkeypatch):
    s = _reload(
        monkeypatch,
        MONGO_URI="mongodb://db:27017",
        MONGO_DB_NAME="x",
        MONGO_SERVER_SELECTION_TIMEOUT_MS="500",
        LOG_LEVEL="debug",
        LOG_FORMAT="JSON",
        LOG_FILE="logs/scraper.log",
    )
    assert s.MONGO_URI == "mongodb://db:27017"
    assert s.MONGO_DB_NAME == "x"
    assert s.MONGO_SERVER_SELECTION_TIMEOUT_MS == 500
    assert s.LOG_LEVEL == "DEBUG"
    assert s.LOG_FORMAT == "json"
    assert s.LOG_FILE == "logs/scraper.log"


def test_log_format_plain_opt_out(monkeypatch):
    s = _reload(monkeypatch, LOG_FORMAT="plain")
    assert s.LOG_FORMAT == "plain"


def test_log_file_strip(monkeypatch):
    s = _reload(monkeypatch, LOG_FILE="  logs/x.log  ")
    assert s.LOG_FILE == "logs/x.log"


def test_sentry_defaults(monkeypatch):
    for k in (
        "SENTRY_ENABLED",
        "SENTRY_DSN",
        "SENTRY_ENVIRONMENT",
        "SENTRY_TRACES_SAMPLE_RATE",
        "SENTRY_RELEASE",
    ):
        monkeypatch.delenv(k, raising=False)
    s = _reload(monkeypatch)
    assert s.SENTRY_ENABLED is False
    assert s.SENTRY_DSN == ""
    assert s.SENTRY_ENVIRONMENT == "production"
    assert s.SENTRY_TRACES_SAMPLE_RATE == 0.0
    assert s.SENTRY_RELEASE == ""


def test_sentry_enabled_truthy(monkeypatch):
    s = _reload(monkeypatch, SENTRY_ENABLED="true", SENTRY_DSN="https://k@o/1")
    assert s.SENTRY_ENABLED is True
    assert s.SENTRY_DSN == "https://k@o/1"


def test_sentry_enabled_empty_string_is_false(monkeypatch):
    # compose `${SENTRY_ENABLED:-}` can inject ""; must coerce to False, NOT raise.
    s = _reload(monkeypatch, SENTRY_ENABLED="")
    assert s.SENTRY_ENABLED is False


def test_sentry_traces_empty_string_is_zero(monkeypatch):
    # bare `SENTRY_TRACES_SAMPLE_RATE=` in a direct python run would crash float("").
    s = _reload(monkeypatch, SENTRY_TRACES_SAMPLE_RATE="")
    assert s.SENTRY_TRACES_SAMPLE_RATE == 0.0
