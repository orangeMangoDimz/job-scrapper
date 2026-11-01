from __future__ import annotations

from pathlib import Path

import mongomock
import pytest
import yaml

from scraper import seed_settings
from scraper.config_loader import validate_job_settings
from scraper.job_settings import JobSettingsStore

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = REPO_ROOT / "seeds" / "job_settings.yaml"
SMALL_SEED = """
keywords: [devops]
sites:
  upwork:
    url_template: "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency"
"""


def _store() -> JobSettingsStore:
    return JobSettingsStore(mongomock.MongoClient()["job_scraper"])


def test_committed_seed_file_is_valid():
    validate_job_settings(yaml.safe_load(SEED_PATH.read_text()))


def test_committed_seed_file_keeps_upwork_location_filter_off():
    settings = yaml.safe_load(SEED_PATH.read_text())

    assert settings["sites"]["upwork"]["filter"] == {}


def test_seed_file_inserts_once(tmp_path: Path):
    path = tmp_path / "seed.yaml"
    path.write_text(SMALL_SEED)
    store = _store()

    assert seed_settings.seed_file(path, store) is True
    assert seed_settings.seed_file(path, store) is False


def test_main_returns_zero_when_seeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    path = tmp_path / "seed.yaml"
    path.write_text(SMALL_SEED)
    monkeypatch.setattr(seed_settings, "open_store", _store)

    assert seed_settings.main(["--file", str(path)]) == 0
    assert "inserted" in capsys.readouterr().out


def test_main_reports_invalid_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    path = tmp_path / "seed.yaml"
    path.write_text("keywords: []\n")
    monkeypatch.setattr(seed_settings, "open_store", _store)

    assert seed_settings.main(["--file", str(path)]) == 2
    assert "keywords" in capsys.readouterr().err


def test_config_file_holds_no_job_settings():
    config = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())

    assert set(config) == {"concurrency", "output_dir", "bot"}
