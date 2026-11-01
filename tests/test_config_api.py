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
    assert set(API_SOURCES) == {"jobstreet", "glints", "linkedin", "upwork"}


def test_delay_seconds_parsed(tmp_path: Path):
    site = load(_write(tmp_path, "    api:\n      delay_seconds: [4, 6]\n")).site("jobstreet")
    assert site is not None
    assert site.api is not None
    assert site.api.delay_seconds == (4.0, 6.0)


def test_delay_seconds_defaults_to_none(tmp_path: Path):
    site = load(_write(tmp_path, "    api: {}\n")).site("jobstreet")
    assert site is not None
    assert site.api is not None
    assert site.api.delay_seconds is None


@pytest.mark.parametrize("bad", ["5", "[6, 4]", "[-1, 2]", "[1, 2, 3]", "[a, b]"])
def test_delay_seconds_must_be_valid_range(tmp_path: Path, bad: str):
    with pytest.raises(ConfigError, match="sites.jobstreet.api.delay_seconds"):
        load(_write(tmp_path, f"    api:\n      delay_seconds: {bad}\n"))


def test_upwork_site_bypasses_the_global_location_filter(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
keywords: [python]
filter:
  location: [jakarta]
sites:
  upwork:
    limit: 30
    filter: {}
    url_template: "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency"
    api:
      locations: [Remote]
"""
    )

    config = load(config_path)

    assert config.filter_for("upwork") == {}
    assert config.limit_for("upwork") == 30
    site = config.site("upwork")
    assert site is not None
    assert site.api is not None
    assert site.api.locations == ("Remote",)
