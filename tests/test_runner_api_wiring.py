from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scraper import runner
from scraper.api.client import DEFAULT_DELAY_SECONDS, DETAIL_DELAY_SECONDS
from scraper.config_loader import ApiConfig, load
from scraper.runner import build_api_callbacks
from scraper.types import Job, empty_job


class RecordingSource:
    name = "stub"
    country_location = None
    instances: list[RecordingSource] = []

    def __init__(self, client: Any) -> None:
        self.client = client
        self.searched: list[str | None] = []
        RecordingSource.instances.append(self)

    def search(self, keyword: str, location: str | None, max_age_hours: int | None, limit: int):
        self.searched.append(location)
        job = empty_job("stub", f"T-{location}", "C")
        job["job_id"] = str(location)
        return [job]

    def detail(self, job: Job) -> str | None:
        return f"detail via {self.client['delay']}"


def _factory(**kwargs: Any) -> dict[str, Any]:
    return {"delay": kwargs.get("delay", DEFAULT_DELAY_SECONDS), "proxy": kwargs.get("proxy")}


def _build(api_cfg: ApiConfig):
    RecordingSource.instances.clear()
    return build_api_callbacks(
        RecordingSource,
        api_cfg,
        "devops",
        proxy_url="http://p:1",
        max_age_hours=72,
        limit=30,
        client_factory=_factory,
    )


def test_search_uses_site_delay_and_detail_uses_short_delay():
    search, detail = _build(ApiConfig(True, ("A", "B"), False, delay_seconds=(4.0, 6.0)))

    assert [j["job_id"] for j in search()] == ["A", "B"]
    assert detail(empty_job("stub", "T", "C")) == f"detail via {DETAIL_DELAY_SECONDS}"

    search_source, detail_source = RecordingSource.instances
    assert search_source.client == {"delay": (4.0, 6.0), "proxy": "http://p:1"}
    assert detail_source.client == {"delay": DETAIL_DELAY_SECONDS, "proxy": "http://p:1"}
    assert detail_source.searched == []


def test_search_falls_back_to_default_delay():
    _build(ApiConfig(True, ("A",), False))
    assert RecordingSource.instances[0].client["delay"] == DEFAULT_DELAY_SECONDS


def test_run_wires_api_callbacks_into_run_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
keywords: [devops]
output_dir: {tmp_path / "out"}
sites:
  jobstreet:
    url_template: "https://id.jobstreet.com/id/{{keyword_slug}}-jobs"
    api:
      locations: [Jakarta Raya]
      delay_seconds: [4, 6]
  glints:
    enabled: false
    url_template: "https://glints.com/id/opportunities/jobs/explore?keyword={{keyword}}"
"""
    )
    built: list[tuple[str, tuple[str, ...], tuple[float, float] | None]] = []
    received: list[dict[str, Any]] = []

    def search() -> list[Job]:
        return []

    def detail(job: Job) -> str | None:
        return None

    def fake_build(source_factory, api_cfg, keyword, **kwargs):
        built.append((keyword, api_cfg.locations, api_cfg.delay_seconds))
        return search, detail

    def fake_run_one(*args: Any, **kwargs: Any) -> None:
        received.append(kwargs)

    monkeypatch.setattr(runner, "refresh_index", lambda: None)
    monkeypatch.setattr(runner, "build_api_callbacks", fake_build)
    monkeypatch.setattr(runner, "run_one", fake_run_one)

    assert runner.run(load(config_path)) == 0
    assert built == [("devops", ("Jakarta Raya",), (4.0, 6.0))]
    assert received == [{"api_search": search, "api_detail": detail}]
