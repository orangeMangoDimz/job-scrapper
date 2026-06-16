# tests/test_log.py
from __future__ import annotations

import importlib
import json
import logging

import pytest


def _reload(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import scraper.settings as settings_mod

    importlib.reload(settings_mod)
    import scraper.log as log_mod

    return importlib.reload(log_mod)


def _clear(monkeypatch):
    for k in ("LOG_LEVEL", "LOG_FORMAT", "LOG_FILE"):
        monkeypatch.delenv(k, raising=False)


def test_get_logger_returns_loguru_logger(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear(monkeypatch)
    log_mod = _reload(monkeypatch)
    from loguru import logger as loguru_logger

    assert log_mod.get_logger() is loguru_logger


def test_default_format_is_json(monkeypatch, tmp_path, capsys):
    # JSON is the default now; loguru-native serialize envelope.
    monkeypatch.chdir(tmp_path)
    _clear(monkeypatch)
    log_mod = _reload(monkeypatch)
    log_mod.get_logger().info("hello {}", "world")
    line = capsys.readouterr().out.strip().splitlines()[-1]
    parsed = json.loads(line)
    assert parsed["record"]["message"] == "hello world"
    assert parsed["record"]["level"]["name"] == "INFO"


def test_plain_format_opt_out(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    _clear(monkeypatch)
    log_mod = _reload(monkeypatch, LOG_FORMAT="plain")
    log_mod.get_logger().info("plain line {}", 7)
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert "plain line 7" in line
    with pytest.raises(json.JSONDecodeError):
        json.loads(line)  # plain mode is not JSON


def test_no_file_by_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear(monkeypatch)
    _reload(monkeypatch).get_logger()
    assert not (tmp_path / "logs").exists()


def test_log_file_opt_in_writes_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear(monkeypatch)
    log_mod = _reload(monkeypatch, LOG_FILE="logs/scraper.log", LOG_FORMAT="plain")
    log_mod.get_logger().info("to file")
    f = tmp_path / "logs" / "scraper.log"
    assert f.is_file()
    assert "to file" in f.read_text(encoding="utf-8")


def test_level_from_env_filters(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    _clear(monkeypatch)
    lg = _reload(monkeypatch, LOG_LEVEL="WARNING", LOG_FORMAT="plain").get_logger()
    lg.info("hidden line")
    lg.warning("shown line")
    out = capsys.readouterr().out
    assert "shown line" in out
    assert "hidden line" not in out


def test_braces_in_third_party_message_do_not_crash(monkeypatch, tmp_path, capsys):
    # Capture-everything: a stdlib log whose %-message expands to text containing
    # literal braces must route through the root InterceptHandler WITHOUT crashing
    # loguru's formatter (advisor trap #1).
    monkeypatch.chdir(tmp_path)
    _clear(monkeypatch)
    log_mod = _reload(monkeypatch, LOG_FORMAT="plain")
    log_mod.get_logger()
    logging.getLogger("third_party").warning("graphql errors: %s", {"code": "X{Y}"})
    out = capsys.readouterr().out
    assert "graphql errors:" in out
    assert "X{Y}" in out


def test_idempotent_single_sink(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    _clear(monkeypatch)
    log_mod = _reload(monkeypatch, LOG_FORMAT="plain")
    log_mod.get_logger()
    log_mod.get_logger()  # second call must NOT add a duplicate sink
    log_mod.get_logger().info("once {}", 1)
    lines = capsys.readouterr().out.strip().splitlines()
    assert sum("once 1" in ln for ln in lines) == 1
