from __future__ import annotations

import pytest
import yaml

from scraper.api.registry import API_SOURCES
from scraper.config_loader import ApiConfig, AppConfig, ConfigError, parse

BASE = """
keywords: [devops]
sites:
  jobstreet:
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs"
"""


def _parse(extra: str) -> AppConfig:
    return parse(yaml.safe_load(BASE + extra), None)


def test_api_block_parsed():
    site = _parse(
        """    api:
      enabled: true
      locations: [Jakarta Raya, Bandung Jawa Barat]
      country_wide: true
""",
    ).site("jobstreet")
    assert site is not None
    assert site.api == ApiConfig(
        enabled=True, locations=("Jakarta Raya", "Bandung Jawa Barat"), country_wide=True
    )


def test_missing_api_block_is_none():
    site = _parse("").site("jobstreet")
    assert site is not None
    assert site.api is None


def test_api_defaults():
    site = _parse("    api: {}\n").site("jobstreet")
    assert site is not None
    assert site.api == ApiConfig(enabled=True, locations=(), country_wide=False)


def test_locations_must_be_list_of_strings():
    with pytest.raises(ConfigError, match="sites.jobstreet.api.locations"):
        _parse("    api:\n      locations: Jakarta\n")


def test_registry_has_api_sites():
    assert set(API_SOURCES) == {"jobstreet", "glints", "linkedin", "upwork"}


def test_delay_seconds_parsed():
    site = _parse("    api:\n      delay_seconds: [4, 6]\n").site("jobstreet")
    assert site is not None
    assert site.api is not None
    assert site.api.delay_seconds == (4.0, 6.0)


def test_delay_seconds_defaults_to_none():
    site = _parse("    api: {}\n").site("jobstreet")
    assert site is not None
    assert site.api is not None
    assert site.api.delay_seconds is None


@pytest.mark.parametrize("bad", ["5", "[6, 4]", "[-1, 2]", "[1, 2, 3]", "[a, b]"])
def test_delay_seconds_must_be_valid_range(bad: str):
    with pytest.raises(ConfigError, match="sites.jobstreet.api.delay_seconds"):
        _parse(f"    api:\n      delay_seconds: {bad}\n")


def test_upwork_site_bypasses_the_global_location_filter():
    config = parse(
        yaml.safe_load(
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
        ),
        None,
    )

    assert config.filter_for("upwork") == {}
    assert config.limit_for("upwork") == 30
    site = config.site("upwork")
    assert site is not None
    assert site.api is not None
    assert site.api.locations == ("Remote",)
