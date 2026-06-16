# tests/test_main_cli.py
from __future__ import annotations

from unittest.mock import patch

from scraper.__main__ import main


def test_bad_config_logs_error_and_returns_2():
    # Behavior: a bad config path is routed through the central logger (not print).
    # Mock get_logger in __main__'s namespace — deterministic, avoids capsys/caplog
    # gotchas (the job-scraper logger has propagate=False so caplog is blind, and its
    # StreamHandler binds stdout at init so capsys can miss it by test order).
    with patch("scraper.__main__.get_logger") as mock_get:
        rc = main(["-c", "does-not-exist.yaml"])
    assert rc == 2
    mock_get.return_value.error.assert_called_once()
    assert "config" in str(mock_get.return_value.error.call_args.args[0]).lower()


def test_main_returns_exit_code_from_run():
    # run() now returns (exit_code, results); main must surface only the int.
    with (
        patch("scraper.__main__.load", return_value=object()),
        patch("scraper.__main__.run", return_value=(0, [])) as mock_run,
    ):
        rc = main(["jobstreet"])
    assert rc == 0
    mock_run.assert_called_once()
