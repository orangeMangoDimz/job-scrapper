from __future__ import annotations

from copy import deepcopy
from typing import Any

import mongomock
import pytest

from mcp_server import server
from scraper.job_settings import JobSettingsStore

SETTINGS: dict[str, Any] = {
    "keywords": ["devops"],
    "limit": 3,
    "sites": {
        "upwork": {
            "enabled": True,
            "url_template": "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency",
        },
        "glints": {
            "enabled": False,
            "url_template": "https://glints.com/id/opportunities/jobs/explore?keyword={keyword}",
        },
    },
}


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Any:
    db = mongomock.MongoClient()["job_scraper"]
    monkeypatch.setattr(server.mongo, "get_database", lambda: db)
    JobSettingsStore(db).seed(deepcopy(SETTINGS))
    return db


def test_get_config_returns_settings_with_version(database: Any):
    result = server.get_config()

    assert result["version"] == 1
    assert result["updated_by"] == "seed"
    assert result["settings"]["keywords"] == ["devops"]


def test_get_config_reports_missing_document(monkeypatch: pytest.MonkeyPatch):
    db = mongomock.MongoClient()["job_scraper"]
    monkeypatch.setattr(server.mongo, "get_database", lambda: db)

    assert "seed.sh" in server.get_config()["error"]


def test_update_config_saves_patch(database: Any):
    result = server.update_config({"limit": 9}, expected_version=1, source="ui")

    assert result["ok"] is True
    assert result["version"] == 2
    assert result["settings"]["limit"] == 9
    assert server.get_config()["updated_by"] == "ui"


def test_update_config_reports_conflict(database: Any):
    result = server.update_config({"limit": 9}, expected_version=5)

    assert result["ok"] is False
    assert result["reason"] == "conflict"


def test_update_config_reports_invalid_patch(database: Any):
    result = server.update_config({"limit": 0})

    assert result["ok"] is False
    assert result["reason"] == "invalid"
    assert "limit" in result["message"]


def test_update_config_refuses_proxy(database: Any):
    result = server.update_config({"proxy": "socks5://localhost:1080"})

    assert result["ok"] is False
    assert result["reason"] == "invalid"


def test_update_config_reports_missing_document(monkeypatch: pytest.MonkeyPatch):
    db = mongomock.MongoClient()["job_scraper"]
    monkeypatch.setattr(server.mongo, "get_database", lambda: db)

    result = server.update_config({"limit": 9})

    assert result["ok"] is False
    assert result["reason"] == "unavailable"


def test_get_config_history_lists_versions(database: Any):
    server.update_config({"limit": 9})

    entries = server.get_config_history()["entries"]

    assert entries == [
        {
            "version": 1,
            "updated_at": entries[0]["updated_at"],
            "updated_by": "seed",
            "keywords": ["devops"],
            "enabled_sites": ["upwork"],
        }
    ]


def test_restore_config_returns_old_settings(database: Any):
    server.update_config({"limit": 9})

    result = server.restore_config(version=1, expected_version=2, source="ui")

    assert result["ok"] is True
    assert result["version"] == 3
    assert result["settings"]["limit"] == 3
