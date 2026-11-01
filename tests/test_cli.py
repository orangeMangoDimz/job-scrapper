from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import mongomock
import pytest

from scraper import __main__ as cli
from scraper.config_loader import PROXY_ENV_VAR
from scraper.job_settings import JobSettingsStore

SETTINGS: dict[str, Any] = {
    "keywords": ["devops"],
    "sites": {
        "upwork": {
            "url_template": "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency",
        }
    },
}


def _config_file(tmp_path: Path) -> str:
    path = tmp_path / "config.yaml"
    path.write_text("concurrency: 1\n")
    return str(path)


def test_cli_runs_with_settings_from_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])
    store.seed(deepcopy(SETTINGS))
    calls: list[tuple[Any, Any, Any]] = []
    monkeypatch.setenv(PROXY_ENV_VAR, "")
    monkeypatch.setattr(cli, "open_store", lambda: store)
    monkeypatch.setattr(
        cli, "run", lambda config, targets, keywords: calls.append((config, targets, keywords)) or 0
    )

    code = cli.main(["--config", _config_file(tmp_path), "-k", "python", "upwork"])

    assert code == 0
    assert calls[0][0].keywords == ("devops",)
    assert calls[0][1] == ["upwork"]
    assert calls[0][2] == ["python"]


def test_cli_reports_missing_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])
    monkeypatch.setenv(PROXY_ENV_VAR, "")
    monkeypatch.setattr(cli, "open_store", lambda: store)

    assert cli.main(["--config", _config_file(tmp_path)]) == 2
    assert "seed.sh" in capsys.readouterr().err
