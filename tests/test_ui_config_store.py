from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ui_server.errors import ConfigInvalidError, ConfigReadOnlyError
from ui_server.schema.config import ConfigUpdateRequest
from ui_server.services.config_store import ConfigStore, deep_merge
from ui_server.settings import Settings

BASE = """# top comment
keywords:
  - devops
limit: 3
# proxy comment
proxy: "socks5://localhost:1080"
sites:
  jobstreet:
    enabled: true
    limit: 5
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs"
"""

PATCH = """proxy: ~
sites:
  jobstreet:
    limit: 30
"""


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        env="dev",
        config_path=tmp_path / "config.yaml",
        dev_patch_path=tmp_path / "patch.yaml",
        dev_merged_path=tmp_path / "merged.yaml",
        backup_dir=tmp_path / "backups",
    )


def _store(tmp_path: Path) -> ConfigStore:
    (tmp_path / "config.yaml").write_text(BASE)
    (tmp_path / "patch.yaml").write_text(PATCH)
    return ConfigStore(_settings(tmp_path))


def test_update_changes_value_and_keeps_comments(tmp_path: Path):
    store = _store(tmp_path)

    store.update(ConfigUpdateRequest(limit=9))

    text = (tmp_path / "config.yaml").read_text()
    assert yaml.safe_load(text)["limit"] == 9
    assert "# top comment" in text
    assert "# proxy comment" in text


def test_update_keeps_list_indent(tmp_path: Path):
    store = _store(tmp_path)

    store.update(ConfigUpdateRequest(limit=9))

    assert "keywords:\n  - devops\n" in (tmp_path / "config.yaml").read_text()


def test_update_writes_in_place(tmp_path: Path):
    store = _store(tmp_path)
    inode_before = (tmp_path / "config.yaml").stat().st_ino

    store.update(ConfigUpdateRequest(limit=9))

    assert (tmp_path / "config.yaml").stat().st_ino == inode_before


def test_update_rewrites_merged_dev_config(tmp_path: Path):
    store = _store(tmp_path)

    store.update(ConfigUpdateRequest(keywords=["python"]))

    merged = yaml.safe_load((tmp_path / "merged.yaml").read_text())
    assert merged["keywords"] == ["python"]
    assert merged["proxy"] is None
    assert merged["sites"]["jobstreet"]["limit"] == 30


def test_update_makes_backup_first(tmp_path: Path):
    store = _store(tmp_path)

    store.update(ConfigUpdateRequest(limit=9))

    backups = list((tmp_path / "backups").iterdir())
    assert len(backups) == 1
    assert yaml.safe_load(backups[0].read_text())["limit"] == 3


def test_update_changes_site_fields(tmp_path: Path):
    store = _store(tmp_path)

    store.update(ConfigUpdateRequest(sites={"jobstreet": {"enabled": False}}))

    config = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert config["sites"]["jobstreet"]["enabled"] is False


def test_update_rejects_unknown_site(tmp_path: Path):
    with pytest.raises(ConfigInvalidError, match="ghost"):
        _store(tmp_path).update(ConfigUpdateRequest(sites={"ghost": {"enabled": True}}))


def test_update_rejects_field_locked_by_patch(tmp_path: Path):
    store = _store(tmp_path)

    with pytest.raises(ConfigInvalidError, match="proxy"):
        store.update(ConfigUpdateRequest(proxy_url="socks5://localhost:9999"))

    assert yaml.safe_load((tmp_path / "config.yaml").read_text())["limit"] == 3


def test_invalid_result_leaves_file_untouched(tmp_path: Path):
    store = _store(tmp_path)
    broken = BASE.replace("id.jobstreet.com", "evil.example.com")
    (tmp_path / "config.yaml").write_text(broken)

    with pytest.raises(ConfigInvalidError):
        store.update(ConfigUpdateRequest(limit=9))

    assert (tmp_path / "config.yaml").read_text() == broken
    assert not (tmp_path / "backups").exists()


def test_invalid_merged_result_leaves_file_untouched(tmp_path: Path):
    store = _store(tmp_path)
    (tmp_path / "patch.yaml").write_text("limit: 0\n")

    with pytest.raises(ConfigInvalidError):
        store.update(ConfigUpdateRequest(max_age_hours=5))

    assert (tmp_path / "config.yaml").read_text() == BASE
    assert not (tmp_path / "backups").exists()


def test_request_rejects_bad_proxy_url():
    with pytest.raises(ValidationError):
        ConfigUpdateRequest(proxy_url="not a proxy")


def test_request_accepts_empty_proxy_url():
    assert ConfigUpdateRequest(proxy_url=None).proxy_url is None


def test_update_is_refused_in_prod(tmp_path: Path):
    settings = Settings(env="prod", password_hash="hash", session_secret="s" * 32)

    with pytest.raises(ConfigReadOnlyError):
        ConfigStore(settings).update(ConfigUpdateRequest(limit=9))


def test_locked_paths_lists_patch_fields(tmp_path: Path):
    assert _store(tmp_path).locked_paths() == ("proxy", "sites.jobstreet.limit")


def test_locked_paths_is_empty_in_prod():
    settings = Settings(env="prod", password_hash="hash", session_secret="s" * 32)

    assert ConfigStore(settings).locked_paths() == ()


def test_deep_merge_replaces_lists_and_merges_maps():
    merged = deep_merge({"a": [1], "b": {"c": 1, "d": 2}}, {"a": [2], "b": {"c": 3}})

    assert merged == {"a": [2], "b": {"c": 3, "d": 2}}
