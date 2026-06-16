# tests/test_config_timeouts.py
from __future__ import annotations

import pytest

from scraper.config import FetchTuning
from scraper.config_loader import ConfigError, _parse_timeouts


def test_defaults_when_absent():
    t = _parse_timeouts(None)
    assert t == FetchTuning()
    assert t.http_seconds == 30
    assert t.playwright_goto_ms == 60_000
    assert t.indeed_api_seconds == 30


def test_partial_override_keeps_other_defaults():
    t = _parse_timeouts({"http_seconds": 10, "playwright_settle_seconds": 1})
    assert t.http_seconds == 10
    assert t.playwright_settle_seconds == 1
    assert t.playwright_goto_ms == 60_000  # untouched default


def test_rejects_non_positive():
    with pytest.raises(ConfigError):
        _parse_timeouts({"http_seconds": 0})


def test_rejects_non_mapping():
    with pytest.raises(ConfigError):
        _parse_timeouts([1, 2, 3])


def test_unknown_key_ignored():
    t = _parse_timeouts({"bogus": 5})
    assert t == FetchTuning()
