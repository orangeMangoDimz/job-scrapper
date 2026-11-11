from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.test_ui_routes import PASSWORD
from ui_server.app import create_app
from ui_server.errors import McpUnavailableError
from ui_server.settings import Settings

LOCAL_URL = "http://127.0.0.1:8090"
CHANNEL_ID = "123456789012345678"
SETTINGS = {
    "configured": True,
    "token_hint": "••••1234",
    "default_channel_id": CHANNEL_ID,
    "mention_user_id": "223456789012345678",
    "message_template": "{title}",
    "max_chars": 1900,
    "updated_at": "2026-11-10T01:00:00+00:00",
}
CHANNELS = [{"id": CHANNEL_ID, "name": "jobs", "guild_id": "1", "guild_name": "Home"}]
RESULTS = [
    {
        "index": 0,
        "kind": "job",
        "title": "A",
        "status": "sent",
        "message_id": "9",
        "error": None,
    }
]
SCRAPE_RESULT = {
    "ok": True,
    "results": [
        {
            "keyword": "devops",
            "sites": [
                {"site": "upwork", "jobs": [{"title": "A"}, {"title": "B"}]},
                {"site": "indeed", "jobs": [{"title": "C"}]},
            ],
        }
    ],
    "errors": [],
}


class FakeGateway:
    def __init__(self) -> None:
        self.is_down = False
        self.responses: dict[str, dict[str, Any]] = {
            "get_discord_settings": SETTINGS,
            "save_discord_settings": {"ok": True, "settings": SETTINGS},
            "test_discord_connection": {"ok": True, "bot_name": "Scraper", "bot_id": "42"},
            "list_discord_channels": {"ok": True, "channels": CHANNELS},
            "preview_discord_message": {"ok": True, "messages": ["hello"]},
            "send_discord_message": {"ok": True, "sent": 1, "failed": 0, "results": RESULTS},
        }
        self.calls: list[str] = []
        self.arguments: dict[str, dict[str, Any]] = {}

    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        self.calls.append(tool)
        self.arguments = {**self.arguments, tool: arguments}
        if self.is_down:
            raise McpUnavailableError()
        return self.responses[tool]


def _failed(reason: str, message: str = "nope") -> dict[str, Any]:
    return {"ok": False, "reason": reason, "message": message}


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    values = {
        "env": "dev",
        "runs_dir": tmp_path / "runs",
        "log_path": tmp_path / "scraper.log",
        "static_dir": tmp_path / "dist",
    }
    return Settings(**{**values, **overrides})


@pytest.fixture
def gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
def app(tmp_path: Path, gateway: FakeGateway) -> FastAPI:
    return create_app(_settings(tmp_path), gateway)


@pytest.fixture
def client(app: FastAPI):
    with TestClient(app, base_url=LOCAL_URL) as test_client:
        yield test_client


@pytest.fixture
def prod_client(tmp_path: Path, gateway: FakeGateway):
    settings = _settings(
        tmp_path,
        env="prod",
        password_hash=PasswordHasher().hash(PASSWORD),
        session_secret="s" * 32,
        domain="testserver",
    )
    with TestClient(create_app(settings, gateway), base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture
def run_id(app: FastAPI, client: TestClient) -> str:
    store = app.state.services.run_store
    record = store.create(("devops",), ("upwork", "indeed"))
    return store.finish(record, SCRAPE_RESULT).id


def test_every_route_needs_login(prod_client: TestClient, gateway: FakeGateway):
    responses = [
        prod_client.get("/api/discord/settings"),
        prod_client.put("/api/discord/settings", json={"max_chars": 10}),
        prod_client.post("/api/discord/test"),
        prod_client.get("/api/discord/channels"),
        prod_client.post("/api/discord/preview", json={"mention": False, "text": "hi"}),
        prod_client.post(
            "/api/discord/send", json={"channel_id": CHANNEL_ID, "mention": False, "text": "hi"}
        ),
    ]

    assert [response.status_code for response in responses] == [401] * 6
    assert gateway.calls == []


def test_read_settings_returns_tool_shape(client: TestClient):
    response = client.get("/api/discord/settings")

    assert response.status_code == 200
    assert response.json() == {"success": True, "data": SETTINGS, "error": None}


def test_read_settings_returns_503_when_mcp_is_down(client: TestClient, gateway: FakeGateway):
    gateway.is_down = True

    assert client.get("/api/discord/settings").status_code == 503


def test_save_settings_sends_only_given_fields(client: TestClient, gateway: FakeGateway):
    response = client.put("/api/discord/settings", json={"max_chars": 1500, "mention_user_id": ""})

    assert response.status_code == 200
    assert response.json()["data"] == SETTINGS
    assert gateway.arguments["save_discord_settings"] == {
        "patch": {"max_chars": 1500, "mention_user_id": ""}
    }


def test_save_settings_rejects_bad_body_before_calling_mcp(
    client: TestClient, gateway: FakeGateway
):
    response = client.put("/api/discord/settings", json={"max_chars": 5000})

    assert response.status_code == 422
    assert "max_chars" in response.json()["error"]
    assert gateway.calls == []


def test_save_settings_maps_invalid_from_tool(client: TestClient, gateway: FakeGateway):
    gateway.responses["save_discord_settings"] = _failed("invalid", "Bad template")

    response = client.put("/api/discord/settings", json={"message_template": "x"})

    assert response.status_code == 422
    assert response.json()["error"] == "Bad template"


def test_save_settings_maps_unavailable_from_tool(client: TestClient, gateway: FakeGateway):
    gateway.responses["save_discord_settings"] = _failed("unavailable", "db down")

    response = client.put("/api/discord/settings", json={"message_template": "x"})

    assert response.status_code == 503
    assert response.json()["error"] == "db down"


def test_test_connection_returns_bot(client: TestClient):
    response = client.post("/api/discord/test")

    assert response.status_code == 200
    assert response.json()["data"] == {"bot_name": "Scraper", "bot_id": "42"}


@pytest.mark.parametrize(
    ("reason", "status", "message"),
    [
        ("not_configured", 409, "Set up Discord in Config first."),
        ("unauthorized", 422, "Discord rejected the bot token."),
        ("unavailable", 503, "nope"),
    ],
)
def test_test_connection_maps_failures(
    client: TestClient, gateway: FakeGateway, reason: str, status: int, message: str
):
    gateway.responses["test_discord_connection"] = _failed(reason)

    response = client.post("/api/discord/test")

    assert response.status_code == status
    assert response.json() == {"success": False, "data": None, "error": message}


def test_channels_returns_list(client: TestClient):
    response = client.get("/api/discord/channels")

    assert response.status_code == 200
    assert response.json()["data"] == {"channels": CHANNELS}


def test_channels_maps_not_configured(client: TestClient, gateway: FakeGateway):
    gateway.responses["list_discord_channels"] = _failed("not_configured")

    response = client.get("/api/discord/channels")

    assert response.status_code == 409


def test_preview_text_passes_text_to_tool(client: TestClient, gateway: FakeGateway):
    response = client.post("/api/discord/preview", json={"mention": True, "text": "hello"})

    assert response.status_code == 200
    assert response.json()["data"] == {"messages": ["hello"]}
    assert gateway.arguments["preview_discord_message"] == {"mention": True, "text": "hello"}


def test_preview_run_jobs_passes_picked_jobs_in_order(
    client: TestClient, gateway: FakeGateway, run_id: str
):
    response = client.post(
        "/api/discord/preview",
        json={"mention": False, "run_id": run_id, "job_indexes": [2, 0]},
    )

    assert response.status_code == 200
    assert gateway.arguments["preview_discord_message"] == {
        "mention": False,
        "jobs": [{"title": "C"}, {"title": "A"}],
    }


def test_preview_maps_invalid_from_tool(client: TestClient, gateway: FakeGateway):
    gateway.responses["preview_discord_message"] = _failed("invalid", "Text is too long")

    response = client.post("/api/discord/preview", json={"mention": True, "text": "hello"})

    assert response.status_code == 422
    assert response.json()["error"] == "Text is too long"


def test_preview_unknown_run_is_404(client: TestClient, gateway: FakeGateway):
    response = client.post(
        "/api/discord/preview",
        json={"mention": False, "run_id": "20261101T010000Z-abc123", "job_indexes": [0]},
    )

    assert response.status_code == 404
    assert gateway.calls == []


def test_preview_malformed_run_id_is_404(client: TestClient):
    response = client.post(
        "/api/discord/preview", json={"mention": False, "run_id": "nope", "job_indexes": [0]}
    )

    assert response.status_code == 404


def test_preview_out_of_range_index_is_422(client: TestClient, gateway: FakeGateway, run_id: str):
    response = client.post(
        "/api/discord/preview",
        json={"mention": False, "run_id": run_id, "job_indexes": [0, 3]},
    )

    assert response.status_code == 422
    assert gateway.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"mention": True},
        {"mention": True, "text": "hi", "run_id": "x", "job_indexes": [0]},
        {"mention": True, "run_id": "x"},
        {"mention": True, "run_id": "x", "job_indexes": []},
        {"mention": True, "run_id": "x", "job_indexes": [1, 1]},
        {"mention": True, "run_id": "x", "job_indexes": list(range(51))},
    ],
)
def test_preview_rejects_bad_body(client: TestClient, gateway: FakeGateway, body: dict):
    response = client.post("/api/discord/preview", json=body)

    assert response.status_code == 422
    assert gateway.calls == []


def test_send_text_returns_counts_and_results(client: TestClient, gateway: FakeGateway):
    response = client.post(
        "/api/discord/send", json={"channel_id": CHANNEL_ID, "mention": True, "text": "hello"}
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"sent": 1, "failed": 0, "results": RESULTS}
    assert gateway.arguments["send_discord_message"] == {
        "channel_id": CHANNEL_ID,
        "mention": True,
        "text": "hello",
    }


def test_send_run_jobs_passes_picked_jobs(client: TestClient, gateway: FakeGateway, run_id: str):
    response = client.post(
        "/api/discord/send",
        json={
            "channel_id": CHANNEL_ID,
            "mention": False,
            "run_id": run_id,
            "job_indexes": [1],
        },
    )

    assert response.status_code == 200
    assert gateway.arguments["send_discord_message"] == {
        "channel_id": CHANNEL_ID,
        "mention": False,
        "jobs": [{"title": "B"}],
    }


@pytest.mark.parametrize(
    ("reason", "status", "message"),
    [
        ("not_configured", 409, "Set up Discord in Config first."),
        ("unauthorized", 422, "Discord rejected the bot token."),
        ("forbidden", 422, "The bot can't post in that channel."),
        ("invalid", 422, "nope"),
        ("unavailable", 503, "nope"),
    ],
)
def test_send_maps_failures(
    client: TestClient, gateway: FakeGateway, reason: str, status: int, message: str
):
    gateway.responses["send_discord_message"] = _failed(reason)

    response = client.post(
        "/api/discord/send", json={"channel_id": CHANNEL_ID, "mention": False, "text": "hi"}
    )

    assert response.status_code == status
    assert response.json()["error"] == message


def test_send_returns_503_when_mcp_is_down(client: TestClient, gateway: FakeGateway):
    gateway.is_down = True

    response = client.post(
        "/api/discord/send", json={"channel_id": CHANNEL_ID, "mention": False, "text": "hi"}
    )

    assert response.status_code == 503


@pytest.mark.parametrize("channel_id", ["123", "1" * 21, "abcdefghijklmnopqr"])
def test_send_rejects_bad_channel_id(client: TestClient, gateway: FakeGateway, channel_id: str):
    response = client.post(
        "/api/discord/send", json={"channel_id": channel_id, "mention": False, "text": "hi"}
    )

    assert response.status_code == 422
    assert gateway.calls == []


def test_send_needs_channel_id(client: TestClient, gateway: FakeGateway):
    response = client.post("/api/discord/send", json={"mention": False, "text": "hi"})

    assert response.status_code == 422
    assert gateway.calls == []
