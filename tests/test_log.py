# tests/test_log.py
from __future__ import annotations


def test_get_logger_returns_named_logger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import importlib

    import scraper.log as log_mod

    importlib.reload(log_mod)

    logger = log_mod.get_logger()
    assert logger.name == "job-scraper"


def test_get_logger_has_two_handlers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import importlib

    import scraper.log as log_mod

    importlib.reload(log_mod)

    logger = log_mod.get_logger()
    assert len(logger.handlers) == 2


def test_get_logger_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import importlib

    import scraper.log as log_mod

    importlib.reload(log_mod)

    logger = log_mod.get_logger()
    count = len(logger.handlers)
    log_mod.get_logger()  # second call
    assert len(logger.handlers) == count


def test_get_logger_creates_logs_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import importlib

    import scraper.log as log_mod

    importlib.reload(log_mod)

    log_mod.get_logger()
    assert (tmp_path / "logs").is_dir()


def test_redact_proxy_url_hides_password():
    from scraper.log import redact_proxy_url

    url = "http://user:secret@proxy.example.com:8080/path"  # pragma: allowlist secret

    redacted = redact_proxy_url(url)

    assert "secret" not in redacted
    assert "user:***" in redacted
    assert "proxy.example.com:8080" in redacted
