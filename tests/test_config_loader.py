# tests/test_config_loader.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scraper.config import FetchTuning
from scraper.config_loader import ConfigError, load
from scraper.types import MANDATORY_FIELDS

_VALID_SITE = 'sites:\n  glints:\n    url_template: "https://glints.com/{keyword}"\n'


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "c.yaml"
    p.write_text(body)
    return p


def test_keywords_dedup_strip(tmp_path):
    cfg = load(_write(tmp_path, 'keywords: [" a ", "a", "b"]\n' + _VALID_SITE))
    assert cfg.keywords == ("a", "b")


def test_singular_keyword(tmp_path):
    cfg = load(_write(tmp_path, 'keyword: "x"\n' + _VALID_SITE))
    assert cfg.keywords == ("x",)


def test_missing_keywords_raises(tmp_path):
    with pytest.raises(ConfigError):
        load(_write(tmp_path, _VALID_SITE))


def test_sites_required(tmp_path):
    with pytest.raises(ConfigError):
        load(_write(tmp_path, 'keywords: ["a"]\n'))


def test_url_host_allowlist(tmp_path):
    with pytest.raises(ConfigError):
        load(
            _write(
                tmp_path,
                'keywords: ["a"]\nsites:\n  x:\n    url_template: "https://evil.com/{keyword}"\n',
            )
        )


def test_url_unknown_placeholder(tmp_path):
    with pytest.raises(ConfigError):
        load(
            _write(
                tmp_path,
                'keywords: ["a"]\nsites:\n  glints:\n    url_template: "https://glints.com/{bogus}"\n',
            )
        )


def test_default_fields_warn_and_drop(tmp_path):
    with patch("scraper.config_loader.get_logger") as gl:
        cfg = load(
            _write(tmp_path, 'keywords: ["a"]\ndefault_fields: ["title", "bogus"]\n' + _VALID_SITE)
        )
    assert cfg.default_fields == ("title",)
    assert gl.return_value.warning.called


def test_filter_lowercase_and_drop_unknown(tmp_path):
    with patch("scraper.config_loader.get_logger"):
        cfg = load(
            _write(
                tmp_path,
                'keywords: ["a"]\nfilter:\n  location: ["Jakarta"]\n  bogus: ["x"]\n' + _VALID_SITE,
            )
        )
    assert cfg.filter == {"location": ["jakarta"]}


def test_max_age_rejects_zero_and_bool(tmp_path):
    with pytest.raises(ConfigError):
        load(_write(tmp_path, 'keywords: ["a"]\nmax_age_hours: 0\n' + _VALID_SITE))
    with pytest.raises(ConfigError):
        load(_write(tmp_path, 'keywords: ["a"]\nmax_age_hours: true\n' + _VALID_SITE))


def test_limit_default_and_str_accepted(tmp_path):
    cfg = load(_write(tmp_path, 'keywords: ["a"]\nlimit: "3"\n' + _VALID_SITE))
    assert cfg.limit == 3
    assert load(_write(tmp_path, 'keywords: ["a"]\n' + _VALID_SITE)).concurrency == 2


def test_proxy_empty_is_none(tmp_path):
    assert load(_write(tmp_path, 'keywords: ["a"]\nproxy: "  "\n' + _VALID_SITE)).proxy is None
    cfg = load(_write(tmp_path, 'keywords: ["a"]\nproxy: "socks5://h:1"\n' + _VALID_SITE))
    assert cfg.proxy is not None
    assert cfg.proxy.url == "socks5://h:1"


def test_timeouts_through_load(tmp_path):
    cfg = load(_write(tmp_path, 'keywords: ["a"]\ntimeouts:\n  http_seconds: 10\n' + _VALID_SITE))
    assert cfg.timeouts.http_seconds == 10 and cfg.timeouts == FetchTuning(http_seconds=10)
    with pytest.raises(ConfigError):
        load(_write(tmp_path, 'keywords: ["a"]\ntimeouts:\n  http_seconds: 0\n' + _VALID_SITE))


def test_appconfig_methods(tmp_path):
    cfg = load(_write(tmp_path, 'keywords: ["a"]\n' + _VALID_SITE))
    assert cfg.keyword == "a"
    assert cfg.enabled_site_names() == ("glints",)
    assert cfg.fields_for("glints") >= MANDATORY_FIELDS
