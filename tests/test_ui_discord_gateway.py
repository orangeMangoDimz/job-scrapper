from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ui_server.errors import (
    ConfigInvalidError,
    DiscordForbiddenError,
    DiscordNotConfiguredError,
    DiscordUnauthorizedError,
    McpUnavailableError,
)
from ui_server.services.mcp_gateway import (
    DISCORD_CALL_TIMEOUT_SECONDS,
    DISCORD_SEND_TIMEOUT_SECONDS,
    READ_TIMEOUT_SECONDS,
    WRITE_TIMEOUT_SECONDS,
    ScraperClient,
)

SETTINGS = {
    "configured": True,
    "token_hint": "••••1234",
    "default_channel_id": None,
    "mention_user_id": None,
    "message_template": "{title}",
    "max_chars": 1900,
    "updated_at": None,
}


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], float]] = []
        self.responses: list[dict[str, Any] | Exception] = []

    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        self.calls.append((tool, arguments, timeout_seconds))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _failed(reason: str, message: str = "nope") -> dict[str, Any]:
    return {"ok": False, "reason": reason, "message": message}


def test_read_discord_settings_returns_tool_result():
    gateway = FakeGateway()
    gateway.responses = [SETTINGS]

    result = asyncio.run(ScraperClient(gateway).read_discord_settings())

    assert result == SETTINGS
    assert gateway.calls == [("get_discord_settings", {}, READ_TIMEOUT_SECONDS)]


def test_read_discord_settings_propagates_unavailable():
    gateway = FakeGateway()
    gateway.responses = [McpUnavailableError()]

    with pytest.raises(McpUnavailableError):
        asyncio.run(ScraperClient(gateway).read_discord_settings())


def test_save_discord_settings_sends_patch_and_returns_settings():
    gateway = FakeGateway()
    gateway.responses = [{"ok": True, "settings": SETTINGS}]

    result = asyncio.run(ScraperClient(gateway).save_discord_settings({"max_chars": 1500}))

    assert result == SETTINGS
    assert gateway.calls == [
        ("save_discord_settings", {"patch": {"max_chars": 1500}}, WRITE_TIMEOUT_SECONDS)
    ]


def test_save_discord_settings_maps_invalid():
    gateway = FakeGateway()
    gateway.responses = [_failed("invalid", "max_chars is wrong")]

    with pytest.raises(ConfigInvalidError, match="max_chars is wrong"):
        asyncio.run(ScraperClient(gateway).save_discord_settings({}))


def test_save_discord_settings_maps_unavailable():
    gateway = FakeGateway()
    gateway.responses = [_failed("unavailable", "db down")]

    with pytest.raises(McpUnavailableError, match="db down"):
        asyncio.run(ScraperClient(gateway).save_discord_settings({}))


def test_test_discord_connection_returns_bot():
    gateway = FakeGateway()
    gateway.responses = [{"ok": True, "bot_name": "Scraper", "bot_id": "42"}]

    result = asyncio.run(ScraperClient(gateway).test_discord_connection())

    assert result == {"bot_name": "Scraper", "bot_id": "42"}
    assert gateway.calls == [("test_discord_connection", {}, DISCORD_CALL_TIMEOUT_SECONDS)]


def test_list_discord_channels_returns_channels():
    gateway = FakeGateway()
    channels = [{"id": "1", "name": "jobs", "guild_id": "2", "guild_name": "Home"}]
    gateway.responses = [{"ok": True, "channels": channels}]

    result = asyncio.run(ScraperClient(gateway).list_discord_channels())

    assert result == channels
    assert gateway.calls == [("list_discord_channels", {}, DISCORD_CALL_TIMEOUT_SECONDS)]


def test_preview_discord_message_text_sends_text_only():
    gateway = FakeGateway()
    gateway.responses = [{"ok": True, "messages": ["hi"]}]

    result = asyncio.run(
        ScraperClient(gateway).preview_discord_message(mention=True, text="hi", jobs=None)
    )

    assert result == ["hi"]
    assert gateway.calls == [
        ("preview_discord_message", {"mention": True, "text": "hi"}, READ_TIMEOUT_SECONDS)
    ]


def test_preview_discord_message_jobs_sends_jobs_only():
    gateway = FakeGateway()
    gateway.responses = [{"ok": True, "messages": ["a", "b"]}]
    jobs = [{"title": "A"}]

    asyncio.run(ScraperClient(gateway).preview_discord_message(mention=False, text=None, jobs=jobs))

    assert gateway.calls == [
        ("preview_discord_message", {"mention": False, "jobs": jobs}, READ_TIMEOUT_SECONDS)
    ]


def test_send_discord_message_returns_summary_and_results():
    gateway = FakeGateway()
    results = [
        {
            "index": 0,
            "kind": "text",
            "title": None,
            "status": "sent",
            "message_id": "9",
            "error": None,
        }
    ]
    gateway.responses = [{"ok": True, "sent": 1, "failed": 0, "results": results}]

    result = asyncio.run(
        ScraperClient(gateway).send_discord_message(
            channel_id="1" * 18, mention=True, text="hi", jobs=None
        )
    )

    assert result == {"sent": 1, "failed": 0, "results": results}
    assert gateway.calls == [
        (
            "send_discord_message",
            {"channel_id": "1" * 18, "mention": True, "text": "hi"},
            DISCORD_SEND_TIMEOUT_SECONDS,
        )
    ]


def test_send_discord_message_jobs_sends_jobs_only():
    gateway = FakeGateway()
    gateway.responses = [{"ok": True, "sent": 0, "failed": 0, "results": []}]
    jobs = [{"title": "A"}]

    asyncio.run(
        ScraperClient(gateway).send_discord_message(
            channel_id="1" * 18, mention=False, text=None, jobs=jobs
        )
    )

    assert gateway.calls[0][1] == {"channel_id": "1" * 18, "mention": False, "jobs": jobs}


@pytest.mark.parametrize(
    ("reason", "error"),
    [
        ("not_configured", DiscordNotConfiguredError),
        ("unauthorized", DiscordUnauthorizedError),
        ("forbidden", DiscordForbiddenError),
        ("invalid", ConfigInvalidError),
        ("unavailable", McpUnavailableError),
        ("surprise", McpUnavailableError),
    ],
)
def test_failed_send_maps_reason(reason: str, error: type[Exception]):
    gateway = FakeGateway()
    gateway.responses = [_failed(reason)]

    with pytest.raises(error):
        asyncio.run(
            ScraperClient(gateway).send_discord_message(
                channel_id="1" * 18, mention=False, text="hi", jobs=None
            )
        )


def test_failed_connection_check_maps_unauthorized():
    gateway = FakeGateway()
    gateway.responses = [_failed("unauthorized")]

    with pytest.raises(DiscordUnauthorizedError):
        asyncio.run(ScraperClient(gateway).test_discord_connection())


def test_failed_channel_list_maps_not_configured():
    gateway = FakeGateway()
    gateway.responses = [_failed("not_configured")]

    with pytest.raises(DiscordNotConfiguredError):
        asyncio.run(ScraperClient(gateway).list_discord_channels())


def test_discord_error_messages_use_spec_text():
    assert DiscordNotConfiguredError().message == "Set up Discord in Config first."
    assert DiscordUnauthorizedError().message == "Discord rejected the bot token."
    assert DiscordForbiddenError().message == "The bot can't post in that channel."
    assert DiscordNotConfiguredError.status_code == 409
    assert DiscordUnauthorizedError.status_code == 422
    assert DiscordForbiddenError.status_code == 422
