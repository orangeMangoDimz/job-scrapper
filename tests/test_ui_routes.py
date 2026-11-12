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

PASSWORD = "correct horse battery"  # pragma: allowlist secret
DEV_LOGIN_KEY = "dev-login-key-for-tests"
LOCAL_URL = "http://127.0.0.1:8090"
SITES = {
    "keywords": ["devops"],
    "limit": 3,
    "sites": [{"name": "upwork", "enabled": True, "url_template": "x", "sample_url": "x"}],
}
CONFIG = {
    "version": 4,
    "updated_at": "2026-11-02T01:00:00+00:00",
    "updated_by": "ui",
    "settings": {
        "keywords": ["devops"],
        "limit": 3,
        "max_age_hours": 72,
        "filter": {"location": "jakarta", "work_type": []},
        "default_fields": ["title"],
        "sites": {
            "upwork": {
                "enabled": True,
                "limit": 30,
                "filter": {},
                "url_template": "x",
                "api": {"locations": ["Remote"]},
            },
            "indeed": {"url_template": "x"},
        },
    },
    "job_fields": ["site", "title", "salary_min"],
    "mandatory_fields": ["site", "title"],
    "location_options": {"jobstreet": [{"label": "Jakarta", "value": "Jakarta Raya"}]},
}
HISTORY = [
    {
        "version": 3,
        "updated_at": "2026-11-01T01:00:00+00:00",
        "updated_by": "seed",
        "keywords": ["devops"],
        "enabled_sites": ["upwork"],
    }
]
SAVED = {"ok": True, "version": 5}
SCRAPE_RESULT = {
    "ok": True,
    "results": [{"keyword": "devops", "sites": [{"site": "upwork", "jobs": [{"title": "A"}]}]}],
    "errors": [],
}


class FakeGateway:
    def __init__(self) -> None:
        self.is_down = False
        self.config = CONFIG
        self.save_result: dict[str, Any] = SAVED
        self.scrape_delay = 0.0
        self.scrape_result: dict[str, Any] = SCRAPE_RESULT
        self.calls: list[str] = []
        self.arguments: dict[str, dict[str, Any]] = {}

    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        self.calls.append(tool)
        self.arguments = {**self.arguments, tool: arguments}
        if self.is_down:
            raise McpUnavailableError()
        if tool == "scrape_jobs":
            await asyncio.sleep(self.scrape_delay)
        return {
            "list_sites": SITES,
            "get_config": self.config,
            "get_config_history": {"entries": HISTORY},
            "scrape_jobs": self.scrape_result,
            "update_config": self.save_result,
            "restore_config": self.save_result,
        }[tool]


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    values = {
        "env": "dev",
        "dev_login_key": DEV_LOGIN_KEY,
        "runs_dir": tmp_path / "runs",
        "log_path": tmp_path / "scraper.log",
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
def guest_client(tmp_path: Path, gateway: FakeGateway):
    app = create_app(_settings(tmp_path), gateway)
    with TestClient(app, base_url=LOCAL_URL) as test_client:
        yield test_client


@pytest.fixture
def client(guest_client: TestClient):
    guest_client.post("/api/auth/login", json={"password": DEV_LOGIN_KEY})
    return guest_client


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


def test_dev_session_needs_login(guest_client: TestClient):
    assert guest_client.get("/api/auth/session").json()["data"] == {
        "auth_required": True,
        "signed_in": False,
    }
    assert guest_client.get("/api/runs").status_code == 401


def test_dev_login_key_opens_api(guest_client: TestClient):
    response = guest_client.post("/api/auth/login", json={"password": DEV_LOGIN_KEY})

    assert response.status_code == 200
    assert guest_client.get("/api/auth/session").json()["data"] == {
        "auth_required": True,
        "signed_in": True,
    }
    assert guest_client.get("/api/runs").status_code == 200


def test_dev_wrong_login_key_returns_401(guest_client: TestClient):
    response = guest_client.post("/api/auth/login", json={"password": "wrong"})

    assert response.status_code == 401
    assert guest_client.get("/api/runs").status_code == 401


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


def test_read_run_returns_raw_and_filtered_payloads(client: TestClient, gateway: FakeGateway):
    gateway.scrape_result = {
        **SCRAPE_RESULT,
        "raw_results": [{"keyword": "devops", "site": "upwork", "payload": {"count": 4}}],
        "filtered_results": [{"keyword": "devops", "site": "upwork", "payload": {"count": 1}}],
    }
    run = _run(client)

    detail = client.get(f"/api/runs/{run['id']}").json()["data"]

    assert detail["payloads"] == [
        {"keyword": "devops", "site": "upwork", "raw": {"count": 4}, "filtered": {"count": 1}}
    ]
    assert detail["jobs"] == [{"title": "A"}]


def test_read_run_without_stored_payloads_returns_an_empty_list(client: TestClient):
    run = _run(client)

    detail = client.get(f"/api/runs/{run['id']}").json()["data"]

    assert detail["payloads"] == []


def test_read_run_survives_malformed_stored_payloads(client: TestClient, gateway: FakeGateway):
    gateway.scrape_result = {**SCRAPE_RESULT, "raw_results": "oops", "filtered_results": [1, None]}
    run = _run(client)

    response = client.get(f"/api/runs/{run['id']}")

    assert response.status_code == 200
    assert response.json()["data"]["payloads"] == []


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


def test_config_read_returns_values_and_version(client: TestClient):
    data = client.get("/api/config").json()["data"]

    assert data["version"] == 4
    assert data["updated_by"] == "ui"
    assert data["is_stale"] is False
    assert data["values"]["filter"] == {"location": ["jakarta"]}
    assert "proxy_url" not in data["values"]


def test_config_read_lists_job_fields_and_the_always_saved_ones(client: TestClient):
    data = client.get("/api/config").json()["data"]

    assert data["job_fields"] == ["site", "title", "salary_min"]
    assert data["mandatory_fields"] == ["site", "title"]


def test_config_read_passes_city_options_through(client: TestClient):
    data = client.get("/api/config").json()["data"]

    assert data["location_options"] == {
        "jobstreet": [{"label": "Jakarta", "value": "Jakarta Raya"}]
    }


def test_config_read_defaults_city_options_to_empty_for_an_older_scraper(
    client: TestClient, gateway: FakeGateway
):
    gateway.config = {k: v for k, v in CONFIG.items() if k != "location_options"}

    assert client.get("/api/config").json()["data"]["location_options"] == {}


def test_config_read_keeps_site_filter_states_apart(client: TestClient):
    sites = client.get("/api/config").json()["data"]["values"]["sites"]

    assert sites[0]["filter"] == {}
    assert sites[0]["api"] == {"locations": ["Remote"]}
    assert sites[1] == {
        "name": "indeed",
        "enabled": True,
        "limit": None,
        "max_age_hours": None,
        "filter": None,
        "fields": None,
        "api": None,
    }


def test_config_read_marks_stale_values_when_mcp_is_down(
    client: TestClient, gateway: FakeGateway
):
    client.get("/api/config")
    gateway.is_down = True

    assert client.get("/api/config").json()["data"]["is_stale"] is True


def test_config_update_sends_only_changed_fields(client: TestClient, gateway: FakeGateway):
    response = client.put(
        "/api/config",
        json={
            "version": 4,
            "limit": 9,
            "sites": {
                "upwork": {
                    "max_age_hours": None,
                    "filter": {"work_type": ["remote"]},
                    "api": {
                        "enabled": True,
                        "locations": ["Remote"],
                        "country_wide": False,
                        "delay_seconds": [4, 6],
                    },
                }
            },
        },
    )

    assert response.status_code == 200
    assert gateway.arguments["update_config"] == {
        "patch": {
            "limit": 9,
            "sites": {
                "upwork": {
                    "max_age_hours": None,
                    "filter": {"work_type": ["remote"]},
                    "api": {
                        "enabled": True,
                        "locations": ["Remote"],
                        "country_wide": False,
                        "delay_seconds": [4.0, 6.0],
                    },
                }
            },
        },
        "expected_version": 4,
        "source": "ui",
    }


def test_config_update_requires_version(client: TestClient):
    assert client.put("/api/config", json={"limit": 9}).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"version": 4, "proxy_url": "socks5://localhost:1080"},
        {"version": 4, "sites": {"upwork": {"url_template": "https://evil.test"}}},
    ],
)
def test_config_update_refuses_fields_the_page_cannot_edit(client: TestClient, body: dict):
    assert client.put("/api/config", json=body).status_code == 422


def _delay_body(delay: list[float]) -> dict:
    api = {"enabled": True, "locations": [], "country_wide": False, "delay_seconds": delay}
    return {"version": 4, "sites": {"jobstreet": {"api": api}}}


@pytest.mark.parametrize(
    "body",
    [
        _delay_body([1, 61]),
        _delay_body([61, 62]),
        {"version": 4, "keywords": ["devops"] * 101},
    ],
)
def test_config_update_refuses_values_over_the_cap(client: TestClient, body: dict):
    assert client.put("/api/config", json=body).status_code == 422


def test_config_update_returns_409_on_conflict(client: TestClient, gateway: FakeGateway):
    gateway.save_result = {"ok": False, "reason": "conflict", "message": "changed"}

    response = client.put("/api/config", json={"version": 4, "limit": 9})

    assert response.status_code == 409
    assert response.json()["error"] == "changed"


def test_config_update_returns_422_on_invalid_settings(client: TestClient, gateway: FakeGateway):
    gateway.save_result = {"ok": False, "reason": "invalid", "message": "bad filter"}

    response = client.put("/api/config", json={"version": 4, "limit": 9})

    assert response.status_code == 422
    assert response.json()["error"] == "bad filter"


def test_config_history_lists_versions(client: TestClient):
    data = client.get("/api/config/history").json()["data"]

    assert data["entries"] == HISTORY


def test_config_restore_sends_versions(client: TestClient, gateway: FakeGateway):
    response = client.post("/api/config/restore", json={"version": 3, "expected_version": 4})

    assert response.status_code == 200
    assert gateway.arguments["restore_config"] == {
        "version": 3,
        "expected_version": 4,
        "source": "ui",
    }


def test_prod_config_needs_login(prod_client: TestClient):
    assert prod_client.get("/api/config").status_code == 401
    assert prod_client.put("/api/config", json={"version": 4, "limit": 9}).status_code == 401
    assert (
        prod_client.post(
            "/api/config/restore", json={"version": 3, "expected_version": 4}
        ).status_code
        == 401
    )


def test_prod_config_can_be_saved_after_login(prod_client: TestClient, gateway: FakeGateway):
    prod_client.post("/api/auth/login", json={"password": PASSWORD})

    response = prod_client.put("/api/config", json={"version": 4, "limit": 9})

    assert response.status_code == 200
    assert "update_config" in gateway.calls


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


def test_spa_paths_fall_back_to_index(tmp_path: Path, gateway: FakeGateway):
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("<html>app</html>")
    app = create_app(_settings(tmp_path), gateway)
    with TestClient(app, base_url=LOCAL_URL) as test_client:
        assert "app" in test_client.get("/config").text
        assert test_client.get("/api/missing").status_code == 404


def test_favicon_files_are_served_instead_of_index(tmp_path: Path, gateway: FakeGateway):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "favicon.svg").write_text("<svg></svg>")
    (dist / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")
    app = create_app(_settings(tmp_path), gateway)
    with TestClient(app, base_url=LOCAL_URL) as test_client:
        svg = test_client.get("/favicon.svg")
        ico = test_client.get("/favicon.ico")

    assert svg.headers["content-type"].startswith("image/svg+xml")
    assert svg.text == "<svg></svg>"
    assert ico.content == b"\x00\x00\x01\x00"
