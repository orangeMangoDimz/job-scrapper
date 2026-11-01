from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import mongomock
import pytest
from pymongo.errors import ServerSelectionTimeoutError

from scraper.config_loader import PROXY_ENV_VAR, ConfigError
from scraper.job_settings import (
    KEEP_HISTORY,
    JobSettingsStore,
    SettingsConflictError,
    SettingsMissingError,
    SettingsUnavailableError,
    load_app_config,
    merge_settings,
)

UPWORK_URL = "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency"
SETTINGS: dict[str, Any] = {
    "keywords": ["devops"],
    "limit": 3,
    "max_age_hours": 72,
    "filter": {"location": ["jakarta"]},
    "sites": {
        "upwork": {"enabled": True, "limit": 30, "filter": {}, "url_template": UPWORK_URL},
        "glints": {
            "enabled": False,
            "limit": 2,
            "url_template": "https://glints.com/id/opportunities/jobs/explore?keyword={keyword}",
        },
    },
}


@pytest.fixture
def store() -> JobSettingsStore:
    job_store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])
    assert job_store.seed(deepcopy(SETTINGS)) is True
    return job_store


def test_merge_replaces_top_level_keys():
    merged = merge_settings(SETTINGS, {"filter": {"work_type": ["remote"]}})

    assert merged["filter"] == {"work_type": ["remote"]}
    assert merged["keywords"] == ["devops"]


def test_merge_changes_one_site_and_keeps_the_rest():
    merged = merge_settings(SETTINGS, {"sites": {"upwork": {"limit": 9}}})

    assert merged["sites"]["upwork"]["limit"] == 9
    assert merged["sites"]["upwork"]["url_template"] == UPWORK_URL
    assert merged["sites"]["glints"] == SETTINGS["sites"]["glints"]


def test_merge_replaces_site_filter_with_empty_filter():
    merged = merge_settings(SETTINGS, {"sites": {"glints": {"filter": {}}}})

    assert merged["sites"]["glints"]["filter"] == {}


def test_merge_removes_site_field_on_none():
    merged = merge_settings(SETTINGS, {"sites": {"upwork": {"filter": None}}})

    assert "filter" not in merged["sites"]["upwork"]


def test_merge_does_not_change_input():
    original = deepcopy(SETTINGS)

    merge_settings(SETTINGS, {"limit": 9, "sites": {"upwork": {"limit": 1}}})

    assert original == SETTINGS


def test_merge_rejects_site_that_is_not_a_mapping():
    with pytest.raises(ConfigError, match="sites.upwork must be a mapping"):
        merge_settings(SETTINGS, {"sites": {"upwork": 3}})


def test_read_returns_seeded_settings(store: JobSettingsStore):
    stored = store.read()

    assert stored.version == 1
    assert stored.updated_by == "seed"
    assert stored.settings["keywords"] == ["devops"]


def test_read_reports_missing_document():
    store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])

    with pytest.raises(SettingsMissingError, match="seed.sh job-settings"):
        store.read()


def test_seed_keeps_existing_document(store: JobSettingsStore):
    store.save({"limit": 9}, 1, "ui")

    assert store.seed(deepcopy(SETTINGS)) is False
    assert store.read().settings["limit"] == 9


def test_seed_rejects_invalid_settings():
    store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])

    with pytest.raises(ConfigError):
        store.seed({"keywords": []})


def test_save_moves_to_next_version_and_keeps_old_one(store: JobSettingsStore):
    saved = store.save({"limit": 9}, 1, "ui")

    assert saved.version == 2
    assert saved.updated_by == "ui"
    assert store.read().settings["limit"] == 9
    history = store.history()
    assert [entry.version for entry in history] == [1]
    assert history[0].settings["limit"] == 3


def test_save_rejects_stale_version(store: JobSettingsStore):
    store.save({"limit": 9}, 1, "ui")

    with pytest.raises(SettingsConflictError):
        store.save({"limit": 10}, 1, "ui")

    assert store.read().settings["limit"] == 9


def test_save_detects_a_write_between_read_and_update(
    store: JobSettingsStore, monkeypatch: pytest.MonkeyPatch
):
    stale = store.read()
    store.save({"limit": 9}, None, "ui")
    monkeypatch.setattr(store, "read", lambda: stale)

    with pytest.raises(SettingsConflictError):
        store.save({"limit": 10}, None, "ui")


def test_save_leaves_document_unchanged_when_invalid(store: JobSettingsStore):
    with pytest.raises(ConfigError):
        store.save({"limit": 0}, 1, "ui")

    assert store.read().version == 1
    assert store.history() == ()


def test_history_keeps_newest_versions(store: JobSettingsStore):
    for limit in range(1, KEEP_HISTORY + 4):
        store.save({"limit": limit}, None, "ui")

    versions = [entry.version for entry in store.history()]

    assert len(versions) == KEEP_HISTORY
    assert versions[0] == KEEP_HISTORY + 3
    assert versions == sorted(versions, reverse=True)


def test_restore_brings_back_settings_as_new_version(store: JobSettingsStore):
    store.save({"limit": 9}, 1, "ui")

    restored = store.restore(1, 2, "ui")

    assert restored.version == 3
    assert store.read().settings["limit"] == 3
    assert [entry.version for entry in store.history()] == [2, 1]


def test_restore_rejects_unknown_version(store: JobSettingsStore):
    with pytest.raises(ConfigError, match="no saved version 8"):
        store.restore(8, 1, "ui")


def test_mongo_failure_hides_connection_details():
    database = MagicMock()
    database.__getitem__.return_value.find_one.side_effect = ServerSelectionTimeoutError(
        "secret-host:27017"
    )

    with pytest.raises(SettingsUnavailableError) as caught:
        JobSettingsStore(database).read()

    assert "secret-host" not in str(caught.value)


def test_load_app_config_joins_file_store_and_proxy(
    store: JobSettingsStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "config.yaml"
    path.write_text("concurrency: 5\n")
    monkeypatch.setenv(PROXY_ENV_VAR, "socks5://localhost:1080")

    config = load_app_config(path, store)

    assert config.concurrency == 5
    assert config.keywords == ("devops",)
    assert config.proxy is not None
    assert config.proxy.url == "socks5://localhost:1080"
    assert config.filter_for("upwork") == {}


def test_load_app_config_stops_when_proxy_is_unset(
    store: JobSettingsStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "config.yaml"
    path.write_text("concurrency: 5\n")
    monkeypatch.delenv(PROXY_ENV_VAR, raising=False)

    with pytest.raises(ConfigError, match=PROXY_ENV_VAR):
        load_app_config(path, store)
