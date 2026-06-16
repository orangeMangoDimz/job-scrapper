# tests/test_observability.py
from __future__ import annotations

import importlib
import sys
import types
from typing import Any
from unittest import mock


def _reload_with_env(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import scraper.settings as settings_mod

    importlib.reload(settings_mod)
    import scraper.observability as obs_mod

    return importlib.reload(obs_mod)


def _install_fake_sentry(monkeypatch):
    fake: Any = types.ModuleType("sentry_sdk")
    fake.init = mock.Mock()
    logging_mod: Any = types.ModuleType("sentry_sdk.integrations.logging")
    logging_mod.LoggingIntegration = mock.Mock(name="LoggingIntegration")
    loguru_mod: Any = types.ModuleType("sentry_sdk.integrations.loguru")
    loguru_mod.LoguruIntegration = mock.Mock(name="LoguruIntegration")
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake)
    monkeypatch.setitem(sys.modules, "sentry_sdk.integrations.logging", logging_mod)
    monkeypatch.setitem(sys.modules, "sentry_sdk.integrations.loguru", loguru_mod)
    return fake


def test_disabled_returns_false_no_init(monkeypatch):
    fake = _install_fake_sentry(monkeypatch)
    obs = _reload_with_env(monkeypatch, SENTRY_ENABLED="false")
    assert obs.init_sentry() is False
    fake.init.assert_not_called()


def test_enabled_without_dsn_returns_false(monkeypatch):
    fake = _install_fake_sentry(monkeypatch)
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    obs = _reload_with_env(monkeypatch, SENTRY_ENABLED="true")
    assert obs.init_sentry() is False
    fake.init.assert_not_called()


def test_enabled_with_dsn_initializes(monkeypatch):
    fake = _install_fake_sentry(monkeypatch)
    obs = _reload_with_env(
        monkeypatch,
        SENTRY_ENABLED="true",
        SENTRY_DSN="https://k@o.ingest.sentry.io/1",
        SENTRY_ENVIRONMENT="test-e2e",
    )
    assert obs.init_sentry() is True
    fake.init.assert_called_once()
    kwargs = fake.init.call_args.kwargs
    assert kwargs["dsn"] == "https://k@o.ingest.sentry.io/1"
    assert kwargs["environment"] == "test-e2e"
    assert kwargs["send_default_pii"] is False
    assert kwargs["include_local_variables"] is False
    assert kwargs["before_send"] is obs._before_send


def test_missing_sentry_sdk_degrades(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)  # None entry → ImportError
    obs = _reload_with_env(monkeypatch, SENTRY_ENABLED="true", SENTRY_DSN="https://k@o/1")
    assert obs.init_sentry() is False  # soft-degrade, no crash


def test_before_send_drops_routine_markers(monkeypatch):
    obs = _reload_with_env(monkeypatch)
    for msg in (
        "[curl_cffi] error on https://x: timeout",
        "[glints:software-engineer] FAILED: no html",
        "[indeed-api] POST error: X",
        "[cloudscraper] error on https://y: 403",
        "[playwright] error on https://z",
    ):
        assert obs._before_send({"logentry": {"message": msg}}, {}) is None


def test_before_send_keeps_genuine_errors(monkeypatch):
    obs = _reload_with_env(monkeypatch)
    event = {"logentry": {"message": "scrape_jobs: mongo insert failed: boom"}}
    assert obs._before_send(event, {}) is event


def test_before_send_fails_open_on_unknown_shape(monkeypatch):
    obs = _reload_with_env(monkeypatch)
    event: dict[str, Any] = {"exception": {"values": []}}  # no logentry/message
    assert obs._before_send(event, {}) is event  # keep — never silently drop
