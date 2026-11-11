from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import mongomock
import pytest
from pymongo.errors import ServerSelectionTimeoutError

from mcp_server import discord_sender, discord_tools, server
from mcp_server.discord_sender import BotIdentity, DiscordFailure

CHANNEL_ID = "123456789012345678"
USER_ID = "98765432109876543"
TOKEN = "abc.def.secret-token-1234"
TEMPLATE = "## {title}\n{company} | {location}\n{url}"
TOOL_NAMES = [
    "get_discord_settings",
    "save_discord_settings",
    "test_discord_connection",
    "list_discord_channels",
    "preview_discord_message",
    "send_discord_message",
]


class FakeClient:
    def __init__(
        self,
        *,
        enter_error: Exception | None = None,
        channel_error: Exception | None = None,
        channels: list[dict[str, Any]] | None = None,
    ) -> None:
        self._enter_error = enter_error
        self._channel_error = channel_error
        self._channels = channels or []
        self.sent: list[tuple[str, str]] = []
        self.mentions: list[str | None] = []
        self.tokens: list[str] = []

    async def __aenter__(self) -> FakeClient:
        if self._enter_error:
            raise self._enter_error
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def identity(self) -> BotIdentity:
        return BotIdentity(name="JobBot", id="555")

    async def channels(self) -> list[dict[str, Any]]:
        return self._channels

    async def check_channel(self, channel_id: str) -> None:
        if self._channel_error:
            raise self._channel_error

    async def send(self, channel_id: str, content: str, mention_user_id: str | None = None) -> str:
        self.sent.append((channel_id, content))
        self.mentions.append(mention_user_id)
        return f"msg-{len(self.sent)}"


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    db: Any = mongomock.MongoClient()["job_scraper"]
    monkeypatch.setattr(server.mongo, "get_database", lambda: db)
    config = tmp_path / "config.yaml"
    config.write_text("bot:\n  max_chars: 1500\n  message_template: |\n    {title} at {company}\n")
    monkeypatch.setattr(discord_tools, "DEFAULT_CONFIG_PATH", config)
    return db


@pytest.fixture
def use_client(monkeypatch: pytest.MonkeyPatch):
    def install(client: FakeClient) -> FakeClient:
        def open_client(token: str) -> FakeClient:
            client.tokens.append(token)
            return client

        monkeypatch.setattr(discord_sender, "open_client", open_client)
        return client

    return install


@pytest.fixture
def configured(database: Any) -> Any:
    discord_tools.save_discord_settings(
        {
            "token": TOKEN,
            "default_channel_id": CHANNEL_ID,
            "mention_user_id": USER_ID,
            "message_template": TEMPLATE,
        }
    )
    return database


def job(index: int = 1) -> dict[str, Any]:
    return {
        "title": f"Job {index}",
        "company": "Acme",
        "location": "Jakarta",
        "url": f"https://example.com/{index}",
    }


def unreachable_database(monkeypatch: pytest.MonkeyPatch) -> None:
    broken = MagicMock()
    for method in ("find_one", "update_one"):
        getattr(broken.__getitem__.return_value, method).side_effect = ServerSelectionTimeoutError(
            "secret-host:27017"
        )
    monkeypatch.setattr(server.mongo, "get_database", lambda: broken)


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_every_tool_is_registered_with_a_description(name: str):
    tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}

    assert name in tools
    assert tools[name].description


def test_get_discord_settings_when_not_configured(database: Any):
    assert discord_tools.get_discord_settings() == {
        "configured": False,
        "token_hint": None,
        "default_channel_id": None,
        "mention_user_id": None,
        "message_template": "{title} at {company}\n",
        "max_chars": 1500,
        "updated_at": None,
    }


def test_get_discord_settings_never_returns_the_token(configured: Any):
    result = discord_tools.get_discord_settings()

    assert result["configured"] is True
    assert result["token_hint"] == "••••1234"
    assert TOKEN not in str(result)


def test_get_discord_settings_reports_store_failure(monkeypatch: pytest.MonkeyPatch):
    unreachable_database(monkeypatch)

    result = discord_tools.get_discord_settings()

    assert set(result) == {"error"}
    assert "secret-host" not in result["error"]


def test_save_discord_settings_returns_masked_settings(database: Any):
    result = discord_tools.save_discord_settings({"token": TOKEN, "max_chars": 900})

    assert result["ok"] is True
    assert result["settings"]["token_hint"] == "••••1234"
    assert result["settings"]["max_chars"] == 900
    assert TOKEN not in str(result)


def test_save_discord_settings_invalid(database: Any):
    result = discord_tools.save_discord_settings({"max_chars": 5000})

    assert result["ok"] is False
    assert result["reason"] == "invalid"
    assert "max_chars" in result["message"]


@pytest.mark.parametrize("token", ["abc def", "abc\ndef"])
def test_save_discord_settings_rejects_a_token_with_whitespace(database: Any, token: str):
    result = discord_tools.save_discord_settings({"token": token})

    assert (result["ok"], result["reason"]) == (False, "invalid")


def test_save_discord_settings_unknown_key_is_invalid(database: Any):
    result = discord_tools.save_discord_settings({"webhook_url": "x"})

    assert (result["ok"], result["reason"]) == (False, "invalid")


def test_save_discord_settings_unavailable(monkeypatch: pytest.MonkeyPatch):
    unreachable_database(monkeypatch)

    result = discord_tools.save_discord_settings({"token": TOKEN})

    assert (result["ok"], result["reason"]) == (False, "unavailable")
    assert "secret-host" not in result["message"]


def test_discord_settings_do_not_touch_job_settings(configured: Any):
    assert "job_settings" not in configured.list_collection_names()
    assert server.get_config().get("error")


def test_test_discord_connection_not_configured(database: Any, use_client):
    client = use_client(FakeClient())

    result = asyncio.run(discord_tools.test_discord_connection())

    assert (result["ok"], result["reason"]) == (False, "not_configured")
    assert client.tokens == []


def test_test_discord_connection_ok(configured: Any, use_client):
    client = use_client(FakeClient())

    result = asyncio.run(discord_tools.test_discord_connection())

    assert result == {"ok": True, "bot_name": "JobBot", "bot_id": "555"}
    assert client.tokens == [TOKEN]


def test_test_discord_connection_unauthorized(configured: Any, use_client):
    use_client(FakeClient(enter_error=DiscordFailure("unauthorized", "Discord rejected the token")))

    result = asyncio.run(discord_tools.test_discord_connection())

    assert result == {
        "ok": False,
        "reason": "unauthorized",
        "message": "Discord rejected the token",
    }


def test_test_discord_connection_unavailable_store(monkeypatch: pytest.MonkeyPatch):
    unreachable_database(monkeypatch)

    result = asyncio.run(discord_tools.test_discord_connection())

    assert (result["ok"], result["reason"]) == (False, "unavailable")


def test_list_discord_channels_not_configured(database: Any, use_client):
    use_client(FakeClient())

    result = asyncio.run(discord_tools.list_discord_channels())

    assert (result["ok"], result["reason"]) == (False, "not_configured")


def test_list_discord_channels_ok(configured: Any, use_client):
    use_client(
        FakeClient(
            channels=[
                {"id": "2", "name": "b", "guild_id": "g", "guild_name": "G", "position": 1},
                {"id": "1", "name": "a", "guild_id": "g", "guild_name": "G", "position": 0},
            ]
        )
    )

    result = asyncio.run(discord_tools.list_discord_channels())

    assert result == {
        "ok": True,
        "channels": [
            {"id": "1", "name": "a", "guild_id": "g", "guild_name": "G"},
            {"id": "2", "name": "b", "guild_id": "g", "guild_name": "G"},
        ],
    }


def test_list_discord_channels_unavailable(configured: Any, use_client):
    use_client(FakeClient(enter_error=DiscordFailure("unavailable", "Discord is unreachable")))

    result = asyncio.run(discord_tools.list_discord_channels())

    assert (result["ok"], result["reason"]) == (False, "unavailable")


def test_preview_works_without_a_token_and_uses_config_defaults(database: Any):
    result = discord_tools.preview_discord_message(False, jobs=[job()])

    assert result == {
        "ok": True,
        "messages": ["Job 1 at Acme\n", "Total: 1 job(s)"],
    }


def test_preview_text_with_mention(configured: Any):
    result = discord_tools.preview_discord_message(True, text="hello")

    assert result == {"ok": True, "messages": [f"<@{USER_ID}>\nhello"]}


@pytest.mark.parametrize(
    "arguments",
    [
        {"text": ""},
        {"text": "a" * 2001},
        {"jobs": []},
        {"jobs": [{"title": "t"}] * 51},
        {"text": "hi", "jobs": [{"title": "t"}]},
        {},
    ],
)
def test_preview_invalid_input(configured: Any, arguments: dict[str, Any]):
    result = discord_tools.preview_discord_message(False, **arguments)

    assert (result["ok"], result["reason"]) == (False, "invalid")
    assert result["message"]


def test_preview_text_over_limit_only_because_of_mention(configured: Any):
    text = "a" * 2000

    assert discord_tools.preview_discord_message(False, text=text)["ok"] is True
    assert discord_tools.preview_discord_message(True, text=text)["reason"] == "invalid"


def test_preview_unavailable_store(monkeypatch: pytest.MonkeyPatch):
    unreachable_database(monkeypatch)

    result = discord_tools.preview_discord_message(False, text="hi")

    assert (result["ok"], result["reason"]) == (False, "unavailable")


def test_preview_matches_what_send_posts(configured: Any, use_client):
    client = use_client(FakeClient())
    jobs = [job(1), job(2)]

    preview = discord_tools.preview_discord_message(True, jobs=jobs)
    asyncio.run(discord_tools.send_discord_message(CHANNEL_ID, True, jobs=jobs))

    assert [content for _, content in client.sent] == preview["messages"]


def test_send_text(configured: Any, use_client):
    client = use_client(FakeClient())

    result = asyncio.run(discord_tools.send_discord_message(CHANNEL_ID, False, text="hello"))

    assert result["ok"] is True
    assert (result["sent"], result["failed"]) == (1, 0)
    assert result["results"] == [
        {
            "index": 0,
            "kind": "text",
            "title": None,
            "status": "sent",
            "message_id": "msg-1",
            "error": None,
        }
    ]
    assert client.sent == [(CHANNEL_ID, "hello")]


def test_send_jobs_posts_one_message_per_job_then_a_summary(configured: Any, use_client):
    client = use_client(FakeClient())

    result = asyncio.run(
        discord_tools.send_discord_message(CHANNEL_ID, True, jobs=[job(1), job(2)])
    )

    assert [entry["kind"] for entry in result["results"]] == ["job", "job", "summary"]
    assert [entry["title"] for entry in result["results"]] == ["Job 1", "Job 2", None]
    assert client.sent[0][1].startswith(f"<@{USER_ID}>\n## Job 1")
    assert client.sent[2][1] == "Total: 2 job(s)"
    assert result["sent"] == 3


def test_send_not_configured(database: Any, use_client):
    client = use_client(FakeClient())

    result = asyncio.run(discord_tools.send_discord_message(CHANNEL_ID, False, text="hi"))

    assert (result["ok"], result["reason"]) == (False, "not_configured")
    assert client.sent == []


@pytest.mark.parametrize("channel_id", ["123", "1" * 21, "abc", ""])
def test_send_rejects_bad_channel_id(configured: Any, use_client, channel_id: str):
    client = use_client(FakeClient())

    result = asyncio.run(discord_tools.send_discord_message(channel_id, False, text="hi"))

    assert (result["ok"], result["reason"]) == (False, "invalid")
    assert "channel_id" in result["message"]
    assert client.sent == []


@pytest.mark.parametrize(
    "arguments",
    [{"text": ""}, {"jobs": []}, {"text": "a", "jobs": [job()]}, {}],
)
def test_send_rejects_invalid_content(configured: Any, use_client, arguments: dict[str, Any]):
    client = use_client(FakeClient())

    result = asyncio.run(discord_tools.send_discord_message(CHANNEL_ID, False, **arguments))

    assert (result["ok"], result["reason"]) == (False, "invalid")
    assert client.sent == []


@pytest.mark.parametrize("reason", ["unauthorized", "forbidden", "unavailable"])
def test_send_reports_failures_before_sending(configured: Any, use_client, reason: str):
    use_client(FakeClient(channel_error=DiscordFailure(reason, "nope")))

    result = asyncio.run(discord_tools.send_discord_message(CHANNEL_ID, False, text="hi"))

    assert result == {"ok": False, "reason": reason, "message": "nope"}


def test_send_unauthorized_on_login(configured: Any, use_client):
    use_client(FakeClient(enter_error=DiscordFailure("unauthorized", "rejected")))

    result = asyncio.run(discord_tools.send_discord_message(CHANNEL_ID, False, text="hi"))

    assert (result["ok"], result["reason"]) == (False, "unauthorized")


def test_send_unavailable_store(monkeypatch: pytest.MonkeyPatch):
    unreachable_database(monkeypatch)

    result = asyncio.run(discord_tools.send_discord_message(CHANNEL_ID, False, text="hi"))

    assert (result["ok"], result["reason"]) == (False, "unavailable")


def test_send_never_allows_a_mention_from_job_text(configured: Any, use_client):
    client = use_client(FakeClient())
    jobs = [job(1), {**job(2), "title": "<@123456789012345678>"}]

    asyncio.run(discord_tools.send_discord_message(CHANNEL_ID, True, jobs=jobs))
    asyncio.run(discord_tools.send_discord_message(CHANNEL_ID, False, jobs=jobs))

    assert client.mentions == [USER_ID, None, None, None, None, None]


@pytest.mark.parametrize("error", [RuntimeError("boom"), KeyError("x"), ValueError(TOKEN)])
def test_unexpected_error_becomes_unavailable_without_leaking(
    configured: Any, use_client, caplog: pytest.LogCaptureFixture, error: Exception
):
    use_client(FakeClient(enter_error=error))

    result = asyncio.run(discord_tools.send_discord_message(CHANNEL_ID, False, text="hi"))

    assert result == {"ok": False, "reason": "unavailable", "message": "Discord request failed"}
    assert TOKEN not in str(result)
    assert any(record.exc_info for record in caplog.records)


def test_unexpected_error_in_connection_test_is_unavailable(configured: Any, use_client):
    use_client(FakeClient(enter_error=RuntimeError("boom")))

    result = asyncio.run(discord_tools.test_discord_connection())

    assert (result["ok"], result["reason"]) == (False, "unavailable")


def test_cron_blocks_every_discord_tool():
    script = (Path(__file__).resolve().parents[1] / "cron" / "run-scraper.sh").read_text()

    for name in TOOL_NAMES:
        assert f"mcp__job-scraper__{name}" in script
    assert "mcp__job-scraper__update_config" in script
    assert "mcp__job-scraper__restore_config" in script
