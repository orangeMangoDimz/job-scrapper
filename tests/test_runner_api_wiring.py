from __future__ import annotations

from typing import Any

from scraper.api.client import DEFAULT_DELAY_SECONDS, DETAIL_DELAY_SECONDS
from scraper.config_loader import ApiConfig
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


def test_detail_delay_is_short():
    low, high = DETAIL_DELAY_SECONDS
    assert (low, high) == (0.3, 0.6)
