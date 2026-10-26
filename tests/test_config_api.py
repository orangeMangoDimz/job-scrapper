from __future__ import annotations

from pathlib import Path

import pytest

from scraper.api.registry import API_SOURCES
from scraper.config_loader import ApiConfig, ConfigError, load

BASE = """
keywords: [devops]
sites:
  jobstreet:
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs"
"""


def _write(tmp_path: Path, extra: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(BASE + extra)
    return path


def test_api_block_parsed(tmp_path: Path):
    path = _write(
        tmp_path,
        """    api:
      enabled: true
      locations: [Jakarta Raya, Bandung Jawa Barat]
      country_wide: true
""",
    )
    site = load(path).site("jobstreet")
    assert site is not None
    assert site.api == ApiConfig(
        enabled=True, locations=("Jakarta Raya", "Bandung Jawa Barat"), country_wide=True
    )


def test_missing_api_block_is_none(tmp_path: Path):
    site = load(_write(tmp_path, "")).site("jobstreet")
    assert site is not None
    assert site.api is None


def test_api_defaults(tmp_path: Path):
    site = load(_write(tmp_path, "    api: {}\n")).site("jobstreet")
    assert site is not None
    assert site.api == ApiConfig(enabled=True, locations=(), country_wide=False)


def test_locations_must_be_list_of_strings(tmp_path: Path):
    with pytest.raises(ConfigError, match="sites.jobstreet.api.locations"):
        load(_write(tmp_path, "    api:\n      locations: Jakarta\n"))


def test_registry_has_api_sites():
    assert set(API_SOURCES) == {"jobstreet", "glints", "linkedin"}
