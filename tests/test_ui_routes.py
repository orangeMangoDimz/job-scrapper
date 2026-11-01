from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from ui_server.app import create_app
from ui_server.errors import McpUnavailableError
from ui_server.settings import Settings

PASSWORD = "correct horse battery"
LOCAL_URL = "http://127.0.0.1:8090"
BASE_CONFIG = """keywords: [devops]
limit: 3
sites:
  upwork:
    enabled: true
    url_template: "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency"
"""
SITES = {
    "keywords": ["devops"],
    "limit": 3,
    "sites": [{"name": "upwork", "enabled": True, "url_template": "x", "sample_url": "x"}],
}
CONFIG = {
    "keywords": ["devops"],
    "limit": 3,
    "max_age_hours": 72,
    "proxy": None,
    "sites": {"upwork": {"enabled": True, "limit": 30, "url_template": "x"}},
}
SCRAPE_RESULT = {
    "ok": True,
    "results": [{"keyword": "devops", "sites": [{"site": "upwork", "jobs": [{"title": "A"}]}]}],
    "errors": [],
}


class FakeGateway:
    def __init__(self) -> None:
        self.is_down = False
        self.config = CONFIG
        self.scrape_delay = 0.0
        self.calls: list[str] = []

    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        self.calls.append(tool)
        if self.is_down:
            raise McpUnavailableError()
        if tool == "scrape_jobs":
            await asyncio.sleep(self.scrape_delay)
        return {"list_sites": SITES, "get_config": self.config, "scrape_jobs": SCRAPE_RESULT}[tool]


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    (tmp_path / "config.yaml").write_text(BASE_CONFIG)
    (tmp_path / "patch.yaml").write_text("proxy: ~\n")
    values = {
        "env": "dev",
        "runs_dir": tmp_path / "runs",
        "log_path": tmp_path / "scraper.log",
        "config_path": tmp_path / "config.yaml",
        "dev_patch_path": tmp_path / "patch.yaml",
        "dev_merged_path": tmp_path / "merged.yaml",
        "backup_dir": tmp_path / "backups",
        "static_dir": tmp_path / "dist",
    }
    return Settings(**{**values, **overrides})


def _prod_settings(tmp_path: Path) -> Settings:
    return _settings(
        tmp_path,
        env="prod",
        password_hash=PasswordHasher().hash(PASSWORD),
        session_secret="s" * 32,
        domain="testserver",
    )


@pytest.fixture
def gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
def client(tmp_path: Path, gateway: FakeGateway):
    app = create_app(_settings(tmp_path), gateway)
    with TestClient(app, base_url=LOCAL_URL) as test_client:
        yield test_client


@pytest.fixture
def prod_client(tmp_path: Path, gateway: FakeGateway):
    app = create_app(_prod_settings(tmp_path), gateway)
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


def _run(client: TestClient) -> dict:
    response = client.post("/api/runs", json={"keywords": ["devops"], "sites": ["upwork"]})
    assert response.status_code == 202
    return response.json()["data"]


def test_unknown_host_is_refused(client: TestClient):
    response = client.get("/api/sites", headers={"host": "evil.example.com"})

    assert response.status_code == 400


def test_unknown_host_is_refused_in_prod(prod_client: TestClient):
    response = prod_client.get("/api/sites", headers={"host": "evil.example.com"})

    assert response.status_code == 400


def test_health_check_host_is_allowed_in_prod(prod_client: TestClient):
    assert prod_client.get("/health", headers={"host": "localhost:8090"}).status_code == 200


def test_health_needs_no_login(prod_client: TestClient):
    assert prod_client.get("/health").json() == {"status": "ok"}


def test_session_reports_login_not_needed_in_dev(client: TestClient):
    assert client.get("/api/auth/session").json()["data"] == {
        "auth_required": False,
        "signed_in": True,
    }


def test_sites_returns_options(client: TestClient):
    data = client.get("/api/sites").json()["data"]

    assert data["keywords"] == ["devops"]
    assert data["sites"] == [{"name": "upwork", "enabled": True}]
    assert data["is_stale"] is False


def test_sites_returns_503_when_mcp_is_down(client: TestClient, gateway: FakeGateway):
    gateway.is_down = True

    response = client.get("/api/sites")

    assert response.status_code == 503
    assert response.json()["success"] is False


def test_start_run_then_read_result(client: TestClient):
    run = _run(client)

    detail = client.get(f"/api/runs/{run['id']}").json()["data"]

    assert detail["record"]["status"] == "succeeded"
    assert detail["record"]["job_count"] == 1
    assert detail["jobs"] == [{"title": "A"}]


def test_list_runs_includes_started_run(client: TestClient):
    run = _run(client)

    runs = client.get("/api/runs").json()["data"]

    assert [item["id"] for item in runs] == [run["id"]]


def test_second_run_is_refused_before_reading_sites(client: TestClient, gateway: FakeGateway):
    gateway.scrape_delay = 0.2
    run = _run(client)
    gateway.calls.clear()

    response = client.post("/api/runs", json={"keywords": ["devops"], "sites": ["upwork"]})

    assert response.status_code == 409
    assert "list_sites" not in gateway.calls
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if client.get(f"/api/runs/{run['id']}").json()["data"]["record"]["status"] != "running":
            break


def test_start_run_rejects_unknown_site(client: TestClient):
    response = client.post("/api/runs", json={"keywords": ["devops"], "sites": ["ghost"]})

    assert response.status_code == 422


def test_start_run_needs_keywords(client: TestClient):
    response = client.post("/api/runs", json={"keywords": [], "sites": ["upwork"]})

    assert response.status_code == 422


def test_unknown_run_returns_404(client: TestClient):
    assert client.get("/api/runs/nope").status_code == 404


def test_config_read_shows_locked_fields(client: TestClient):
    data = client.get("/api/config").json()["data"]

    assert data["read_only"] is False
    assert data["locked"] == ["proxy"]
    assert data["values"]["sites"] == [{"name": "upwork", "enabled": True, "limit": 30}]


def test_config_read_hides_proxy_credentials(client: TestClient, gateway: FakeGateway):
    gateway.config = {**CONFIG, "proxy": "socks5://user:secret@host:1080"}

    data = client.get("/api/config").json()["data"]

    assert data["values"]["proxy_url"] == "socks5://***@host:1080"


def test_config_update_writes_file(client: TestClient, tmp_path: Path):
    response = client.put("/api/config", json={"limit": 9})

    assert response.status_code == 200
    assert "limit: 9" in (tmp_path / "config.yaml").read_text()


def test_cross_site_write_is_refused(client: TestClient):
    response = client.put(
        "/api/config", json={"limit": 9}, headers={"sec-fetch-site": "cross-site"}
    )

    assert response.status_code == 403


def test_prod_requires_login(prod_client: TestClient):
    assert prod_client.get("/api/runs").status_code == 401
    assert prod_client.get("/api/logs/stream").status_code == 401


def test_prod_login_opens_api_and_sets_safe_cookie(prod_client: TestClient):
    response = prod_client.post("/api/auth/login", json={"password": PASSWORD})

    cookie = response.headers["set-cookie"].lower()
    assert response.status_code == 200
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=strict" in cookie
    assert prod_client.get("/api/runs").status_code == 200


def test_prod_wrong_password_returns_401(prod_client: TestClient):
    response = prod_client.post("/api/auth/login", json={"password": "wrong"})

    assert response.status_code == 401


def test_prod_logout_clears_session(prod_client: TestClient):
    prod_client.post("/api/auth/login", json={"password": PASSWORD})

    prod_client.post("/api/auth/logout")

    assert prod_client.get("/api/runs").status_code == 401


def test_prod_config_is_read_only(prod_client: TestClient):
    prod_client.post("/api/auth/login", json={"password": PASSWORD})

    assert prod_client.get("/api/config").json()["data"]["read_only"] is True
    assert prod_client.put("/api/config", json={"limit": 9}).status_code == 403


def test_spa_paths_fall_back_to_index(tmp_path: Path, gateway: FakeGateway):
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("<html>app</html>")
    app = create_app(_settings(tmp_path), gateway)
    with TestClient(app, base_url=LOCAL_URL) as test_client:
        assert "app" in test_client.get("/config").text
        assert test_client.get("/api/missing").status_code == 404
