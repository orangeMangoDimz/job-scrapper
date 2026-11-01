from __future__ import annotations

from pathlib import Path

import pytest

from scraper.config_loader import (
    PROXY_ENV_VAR,
    ConfigError,
    parse,
    read_machine_settings,
    resolve_proxy_url,
    validate_job_settings,
)

SETTINGS = {
    "keywords": ["devops"],
    "limit": 3,
    "sites": {"jobstreet": {"url_template": "https://id.jobstreet.com/id/{keyword_slug}-jobs"}},
}


def test_parse_builds_config_with_proxy():
    config = parse({**SETTINGS, "concurrency": 4}, "socks5://localhost:1080")

    assert config.keywords == ("devops",)
    assert config.concurrency == 4
    assert config.proxy is not None
    assert config.proxy.url == "socks5://localhost:1080"


def test_parse_without_proxy():
    assert parse(SETTINGS, None).proxy is None


def test_read_machine_settings_reads_mapping(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("concurrency: 5\n")

    assert read_machine_settings(path) == {"concurrency": 5}


def test_read_machine_settings_requires_file(tmp_path: Path):
    with pytest.raises(ConfigError, match="config file not found"):
        read_machine_settings(tmp_path / "missing.yaml")


def test_resolve_proxy_url_rejects_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(PROXY_ENV_VAR, raising=False)

    with pytest.raises(ConfigError, match=PROXY_ENV_VAR):
        resolve_proxy_url()


def test_resolve_proxy_url_treats_empty_as_direct(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(PROXY_ENV_VAR, "  ")

    assert resolve_proxy_url() is None


def test_resolve_proxy_url_returns_value(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(PROXY_ENV_VAR, " socks5://localhost:1080 ")

    assert resolve_proxy_url() == "socks5://localhost:1080"


def test_validate_job_settings_accepts_valid_settings():
    validate_job_settings(SETTINGS)


def test_validate_job_settings_rejects_machine_keys():
    with pytest.raises(ConfigError, match="not a job setting: proxy"):
        validate_job_settings({**SETTINGS, "proxy": "socks5://localhost:1080"})


def test_validate_job_settings_rejects_bad_values():
    with pytest.raises(ConfigError, match="'limit' must be >= 1"):
        validate_job_settings({**SETTINGS, "limit": 0})
