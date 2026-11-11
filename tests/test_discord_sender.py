from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import aiohttp
import discord
import pytest

from mcp_server import discord_sender
from mcp_server.discord_messages import OutgoingMessage
from mcp_server.discord_sender import (
    DiscordFailure,
    DiscordRestClient,
    fetch_channels,
    fetch_identity,
    post_messages,
)

CHANNEL_ID = "123456789012345678"
USER_ID = "98765432109876543"


def http_error(
    cls: type[discord.HTTPException], status: int, text: str = "message"
) -> discord.HTTPException:
    response = MagicMock()
    response.status = status
    response.reason = "reason"
    return cls(response, text)


class FakeClient:
    def __init__(
        self,
        *,
        identity: tuple[str, str] = ("JobBot", "555"),
        channels: list[dict[str, Any]] | None = None,
        enter_error: Exception | None = None,
        channel_error: Exception | None = None,
        send_errors: dict[int, Exception] | None = None,
        hang_on: int | None = None,
    ) -> None:
        self._identity = identity
        self._channels = channels or []
        self._enter_error = enter_error
        self._channel_error = channel_error
        self._send_errors = send_errors or {}
        self._hang_on = hang_on
        self.sent: list[tuple[str, str]] = []
        self.mentions: list[str | None] = []
        self.closed = False

    async def __aenter__(self) -> FakeClient:
        if self._enter_error:
            raise self._enter_error
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self.closed = True

    async def identity(self) -> discord_sender.BotIdentity:
        return discord_sender.BotIdentity(name=self._identity[0], id=self._identity[1])

    async def channels(self) -> list[dict[str, Any]]:
        return self._channels

    async def check_channel(self, channel_id: str) -> None:
        if self._channel_error:
            raise self._channel_error

    async def send(self, channel_id: str, content: str, mention_user_id: str | None = None) -> str:
        call = len(self.sent)
        self.sent.append((channel_id, content))
        self.mentions.append(mention_user_id)
        if call == self._hang_on:
            await asyncio.sleep(3600)
        if call in self._send_errors:
            raise self._send_errors[call]
        return f"msg-{call}"


@pytest.fixture
def use_client(monkeypatch: pytest.MonkeyPatch):
    def install(client: FakeClient) -> FakeClient:
        monkeypatch.setattr(discord_sender, "open_client", lambda token: client)
        return client

    return install


def messages(*kinds: str) -> list[OutgoingMessage]:
    return [
        OutgoingMessage(kind=kind, title=f"t{i}" if kind == "job" else None, content=f"c{i}")  # type: ignore[arg-type]
        for i, kind in enumerate(kinds)
    ]


def test_fetch_identity_returns_the_bot(use_client):
    use_client(FakeClient(identity=("JobBot", "555")))

    result = asyncio.run(fetch_identity("token"))

    assert result == {"ok": True, "bot_name": "JobBot", "bot_id": "555"}


def test_fetch_identity_failure_carries_reason(use_client):
    use_client(FakeClient(enter_error=DiscordFailure("unauthorized", "Discord rejected the token")))

    with pytest.raises(DiscordFailure) as caught:
        asyncio.run(fetch_identity("token"))

    assert caught.value.reason == "unauthorized"
    assert caught.value.as_result() == {
        "ok": False,
        "reason": "unauthorized",
        "message": "Discord rejected the token",
    }


def test_fetch_channels_sorts_by_guild_name_then_position(use_client):
    use_client(
        FakeClient(
            channels=[
                {"id": "3", "name": "c", "guild_id": "g2", "guild_name": "Beta", "position": 0},
                {"id": "2", "name": "b", "guild_id": "g1", "guild_name": "alpha", "position": 5},
                {"id": "1", "name": "a", "guild_id": "g1", "guild_name": "alpha", "position": 1},
            ]
        )
    )

    result = asyncio.run(fetch_channels("token"))

    assert result["ok"] is True
    assert [channel["id"] for channel in result["channels"]] == ["1", "2", "3"]
    assert set(result["channels"][0]) == {"id", "name", "guild_id", "guild_name"}


def test_post_messages_sends_each_message_in_order(use_client):
    client = use_client(FakeClient())

    result = asyncio.run(post_messages("token", CHANNEL_ID, messages("job", "job", "summary")))

    assert [content for _, content in client.sent[:2]] == ["c0", "c1"]
    assert result["ok"] is True
    assert (result["sent"], result["failed"]) == (3, 0)
    assert result["results"][0] == {
        "index": 0,
        "kind": "job",
        "title": "t0",
        "status": "sent",
        "message_id": "msg-0",
        "error": None,
    }
    assert client.closed is True


def test_summary_is_posted_as_given_even_when_jobs_fail(use_client):
    client = use_client(
        FakeClient(
            send_errors={
                0: DiscordFailure("unavailable", "boom"),
                1: DiscordFailure("unavailable", "boom"),
            }
        )
    )

    result = asyncio.run(post_messages("token", CHANNEL_ID, messages("job", "job", "summary")))

    assert [content for _, content in client.sent] == ["c0", "c1", "c2"]
    assert (result["sent"], result["failed"]) == (1, 2)
    assert [entry["kind"] for entry in result["results"]] == ["job", "job", "summary"]


def test_one_failed_message_does_not_stop_the_others(use_client):
    client = use_client(FakeClient(send_errors={0: DiscordFailure("forbidden", "no access")}))

    result = asyncio.run(post_messages("token", CHANNEL_ID, messages("job", "job")))

    assert len(client.sent) == 2
    assert [entry["status"] for entry in result["results"]] == ["failed", "sent"]
    assert result["results"][0]["message_id"] is None
    assert result["results"][0]["error"]


def test_auth_failure_midway_stops_everything(use_client):
    client = use_client(FakeClient(send_errors={1: DiscordFailure("unauthorized", "rejected")}))

    result = asyncio.run(post_messages("token", CHANNEL_ID, messages("job", "job", "job")))

    assert len(client.sent) == 2
    assert [entry["status"] for entry in result["results"]] == ["sent", "failed", "failed"]
    assert (result["sent"], result["failed"]) == (1, 2)


def test_channel_failure_aborts_before_sending(use_client):
    client = use_client(FakeClient(channel_error=DiscordFailure("forbidden", "no access")))

    with pytest.raises(DiscordFailure) as caught:
        asyncio.run(post_messages("token", CHANNEL_ID, messages("text")))

    assert caught.value.reason == "forbidden"
    assert client.sent == []
    assert client.closed is True


class FakeTextChannel:
    def __init__(self, channel_id: int, name: str, position: int) -> None:
        self.id = channel_id
        self.name = name
        self.position = position
        self.sent: list[dict[str, Any]] = []
        self.error: Exception | None = None

    async def send(self, content: str, **kwargs: Any) -> Any:
        if self.error:
            raise self.error
        self.sent.append({"content": content, **kwargs})
        return SimpleNamespace(id=777)


class FakeGuild:
    def __init__(self, guild_id: int, name: str, channels: list[Any]) -> None:
        self.id = guild_id
        self.name = name
        self._channels = channels

    async def fetch_channels(self) -> list[Any]:
        return self._channels


class FakeDiscordClient:
    last: FakeDiscordClient

    def __init__(self, *, intents: Any, max_ratelimit_timeout: float | None = None) -> None:
        self.intents = intents
        self.max_ratelimit_timeout = max_ratelimit_timeout
        self.user = SimpleNamespace(name="JobBot", id=555)
        self.login_error: Exception | None = None
        self.guilds: list[FakeGuild] = []
        self.channel: Any = None
        self.channel_error: Exception | None = None
        self.closed = False
        self.logged_in_with: str | None = None
        FakeDiscordClient.last = self

    async def login(self, token: str) -> None:
        self.logged_in_with = token
        if self.login_error:
            raise self.login_error

    async def close(self) -> None:
        self.closed = True

    async def fetch_guilds(self, *, limit: int | None = None) -> AsyncIterator[FakeGuild]:
        for guild in self.guilds:
            yield guild

    async def fetch_channel(self, channel_id: int) -> Any:
        if self.channel_error:
            raise self.channel_error
        return self.channel


@pytest.fixture
def fake_discord(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(discord_sender.discord, "Client", FakeDiscordClient)
    monkeypatch.setattr(discord_sender.discord, "TextChannel", FakeTextChannel)
    return FakeDiscordClient


def run_with_client(token: str, action):
    async def runner():
        async with DiscordRestClient(token) as client:
            return await action(client)

    return asyncio.run(runner())


def test_rest_client_uses_no_gateway_intents_and_closes(fake_discord):
    run_with_client("secret", lambda client: client.identity())

    assert fake_discord.last.intents == discord.Intents.none()
    assert fake_discord.last.logged_in_with == "secret"
    assert fake_discord.last.closed is True


def test_rest_client_identity(fake_discord):
    identity = run_with_client("secret", lambda client: client.identity())

    assert identity == discord_sender.BotIdentity(name="JobBot", id="555")


@pytest.mark.parametrize(
    "error",
    [discord.LoginFailure("bad token"), http_error(discord.HTTPException, 401)],
)
def test_login_rejection_is_unauthorized_and_still_closes(fake_discord, monkeypatch, error):
    original_init = FakeDiscordClient.__init__

    def init(self: FakeDiscordClient, **options: Any) -> None:
        original_init(self, **options)
        self.login_error = error

    monkeypatch.setattr(FakeDiscordClient, "__init__", init)

    with pytest.raises(DiscordFailure) as caught:
        run_with_client("secret", lambda client: client.identity())

    assert caught.value.reason == "unauthorized"
    assert "secret" not in caught.value.message
    assert fake_discord.last.closed is True


@pytest.mark.parametrize(
    "error",
    [
        http_error(discord.HTTPException, 500),
        aiohttp.ClientConnectionError("boom"),
        OSError("down"),
        TimeoutError(),
    ],
)
def test_login_network_problem_is_unavailable(fake_discord, monkeypatch, error):
    original_init = FakeDiscordClient.__init__

    def init(self: FakeDiscordClient, **options: Any) -> None:
        original_init(self, **options)
        self.login_error = error

    monkeypatch.setattr(FakeDiscordClient, "__init__", init)

    with pytest.raises(DiscordFailure) as caught:
        run_with_client("secret", lambda client: client.identity())

    assert caught.value.reason == "unavailable"


def test_rest_client_lists_text_channels_with_guild_details(fake_discord):
    async def action(client: DiscordRestClient):
        fake_discord.last.guilds = [
            FakeGuild(
                10,
                "Guild",
                [FakeTextChannel(1, "general", 2), SimpleNamespace(id=2, name="voice", position=0)],
            )
        ]
        return await client.channels()

    channels = run_with_client("secret", action)

    assert channels == [
        {"id": "1", "name": "general", "guild_id": "10", "guild_name": "Guild", "position": 2}
    ]


def test_rest_client_channel_listing_failure_is_unavailable(fake_discord):
    async def action(client: DiscordRestClient):
        guild = FakeGuild(10, "Guild", [])

        async def broken() -> list[Any]:
            raise http_error(discord.HTTPException, 500)

        guild.fetch_channels = broken  # type: ignore[method-assign]
        fake_discord.last.guilds = [guild]
        return await client.channels()

    with pytest.raises(DiscordFailure) as caught:
        run_with_client("secret", action)

    assert caught.value.reason == "unavailable"


def test_rest_client_sends_with_safe_mentions(fake_discord):
    channel = FakeTextChannel(1, "general", 0)

    async def action(client: DiscordRestClient):
        fake_discord.last.channel = channel
        await client.check_channel(CHANNEL_ID)
        return await client.send(CHANNEL_ID, "hello")

    message_id = run_with_client("secret", action)

    assert message_id == "777"
    mentions = channel.sent[0]["allowed_mentions"]
    assert mentions.everyone is False
    assert mentions.roles is False
    assert mentions.users is False


@pytest.mark.parametrize(
    "error",
    [http_error(discord.Forbidden, 403), http_error(discord.NotFound, 404)],
)
def test_missing_or_forbidden_channel_is_forbidden(fake_discord, error):
    async def action(client: DiscordRestClient):
        fake_discord.last.channel_error = error
        await client.check_channel(CHANNEL_ID)

    with pytest.raises(DiscordFailure) as caught:
        run_with_client("secret", action)

    assert caught.value.reason == "forbidden"


def test_channel_that_cannot_receive_messages_is_forbidden(fake_discord):
    async def action(client: DiscordRestClient):
        fake_discord.last.channel = SimpleNamespace(id=1)
        await client.check_channel(CHANNEL_ID)

    with pytest.raises(DiscordFailure) as caught:
        run_with_client("secret", action)

    assert caught.value.reason == "forbidden"


def test_channel_lookup_server_error_is_unavailable(fake_discord):
    async def action(client: DiscordRestClient):
        fake_discord.last.channel_error = http_error(discord.HTTPException, 500)
        await client.check_channel(CHANNEL_ID)

    with pytest.raises(DiscordFailure) as caught:
        run_with_client("secret", action)

    assert caught.value.reason == "unavailable"


def test_channel_lookup_unauthorized_is_unauthorized(fake_discord):
    async def action(client: DiscordRestClient):
        fake_discord.last.channel_error = http_error(discord.HTTPException, 401)
        await client.check_channel(CHANNEL_ID)

    with pytest.raises(DiscordFailure) as caught:
        run_with_client("secret", action)

    assert caught.value.reason == "unauthorized"


def test_send_maps_rejections_to_failures(fake_discord):
    channel = FakeTextChannel(1, "general", 0)
    channel.error = http_error(discord.Forbidden, 403)

    async def action(client: DiscordRestClient):
        fake_discord.last.channel = channel
        await client.check_channel(CHANNEL_ID)
        await client.send(CHANNEL_ID, "hello")

    with pytest.raises(DiscordFailure) as caught:
        run_with_client("secret", action)

    assert caught.value.reason == "forbidden"


def test_rest_client_allows_only_the_given_user_to_be_mentioned(fake_discord):
    channel = FakeTextChannel(1, "general", 0)

    async def action(client: DiscordRestClient):
        fake_discord.last.channel = channel
        await client.check_channel(CHANNEL_ID)
        return await client.send(CHANNEL_ID, f"<@{USER_ID}>\nhello", USER_ID)

    run_with_client("secret", action)

    mentions = channel.sent[0]["allowed_mentions"]
    assert mentions.everyone is False
    assert mentions.roles is False
    assert [user.id for user in mentions.users] == [int(USER_ID)]


def test_rest_client_blocks_a_mention_inside_job_text(fake_discord):
    channel = FakeTextChannel(1, "general", 0)

    async def action(client: DiscordRestClient):
        fake_discord.last.channel = channel
        await client.check_channel(CHANNEL_ID)
        return await client.send(CHANNEL_ID, "## <@123456789012345678>", None)

    run_with_client("secret", action)

    mentions = channel.sent[0]["allowed_mentions"]
    assert (mentions.everyone, mentions.roles, mentions.users) == (False, False, False)


def test_post_messages_passes_the_mention_user_id_of_each_message(use_client):
    client = use_client(FakeClient())
    outgoing = [
        OutgoingMessage(kind="job", title="a", content="c0", mention_user_id=USER_ID),
        OutgoingMessage(kind="job", title="<@123456789012345678>", content="c1"),
        OutgoingMessage(kind="summary", title=None, content="c2"),
    ]

    asyncio.run(post_messages("token", CHANNEL_ID, outgoing))

    assert client.mentions == [USER_ID, None, None]


def test_rest_client_limits_rate_limit_waits(fake_discord):
    run_with_client("secret", lambda client: client.identity())

    assert fake_discord.last.max_ratelimit_timeout == 30.0


def test_rate_limited_send_is_a_failure_that_names_the_wait(fake_discord):
    channel = FakeTextChannel(1, "general", 0)
    channel.error = discord.RateLimited(45.0)

    async def action(client: DiscordRestClient):
        fake_discord.last.channel = channel
        await client.check_channel(CHANNEL_ID)
        await client.send(CHANNEL_ID, "hello")

    with pytest.raises(DiscordFailure) as caught:
        run_with_client("secret", action)

    assert caught.value.reason == "unavailable"
    assert "45" in caught.value.message
    assert "rate limit" in caught.value.message


def test_rate_limited_login_is_unavailable(fake_discord, monkeypatch):
    original_init = FakeDiscordClient.__init__

    def init(self: FakeDiscordClient, **options: Any) -> None:
        original_init(self, **options)
        self.login_error = discord.RateLimited(45.0)

    monkeypatch.setattr(FakeDiscordClient, "__init__", init)

    with pytest.raises(DiscordFailure) as caught:
        run_with_client("secret", lambda client: client.identity())

    assert caught.value.reason == "unavailable"
    assert fake_discord.last.closed is True


def test_rate_limited_message_fails_and_the_rest_continue(use_client):
    client = use_client(
        FakeClient(
            send_errors={
                0: discord_sender._failure_from_exception(discord.RateLimited(45.0), channel=True)
            }
        )
    )

    result = asyncio.run(post_messages("token", CHANNEL_ID, messages("job", "job")))

    assert [entry["status"] for entry in result["results"]] == ["failed", "sent"]
    assert "rate limit" in result["results"][0]["error"]
    assert len(client.sent) == 2


def test_deadline_stops_posting_and_fails_the_rest(use_client, monkeypatch):
    monkeypatch.setattr(discord_sender, "SEND_DEADLINE_SECONDS", 0.05)
    client = use_client(FakeClient(hang_on=1))

    result = asyncio.run(
        post_messages("token", CHANNEL_ID, messages("job", "job", "job", "summary"))
    )

    assert result["ok"] is True
    assert (result["sent"], result["failed"]) == (1, 3)
    assert [entry["status"] for entry in result["results"]] == [
        "sent",
        "failed",
        "failed",
        "failed",
    ]
    assert [entry["index"] for entry in result["results"]] == [0, 1, 2, 3]
    assert {entry["error"] for entry in result["results"][1:]} == {"Stopped: send took too long"}
    assert len(client.sent) == 2
    assert client.closed is True


def test_deadline_is_below_the_gateway_timeout():
    assert 100 <= discord_sender.SEND_DEADLINE_SECONDS < 180


def test_unexpected_error_during_login_still_closes_the_client(fake_discord, monkeypatch):
    original_init = FakeDiscordClient.__init__

    def init(self: FakeDiscordClient, **options: Any) -> None:
        original_init(self, **options)
        self.login_error = RuntimeError("boom")

    monkeypatch.setattr(FakeDiscordClient, "__init__", init)

    with pytest.raises(RuntimeError):
        run_with_client("secret", lambda client: client.identity())

    assert fake_discord.last.closed is True


def test_http_error_text_is_included_in_the_failure(fake_discord):
    channel = FakeTextChannel(1, "general", 0)
    channel.error = http_error(discord.HTTPException, 400, "Cannot send an empty message")

    async def action(client: DiscordRestClient):
        fake_discord.last.channel = channel
        await client.check_channel(CHANNEL_ID)
        await client.send(CHANNEL_ID, "hello")

    with pytest.raises(DiscordFailure) as caught:
        run_with_client("secret", action)

    assert caught.value.message == "Discord returned an error (400): Cannot send an empty message"


def test_http_error_text_is_trimmed_and_flattened():
    exc = http_error(discord.HTTPException, 400, "line one\n" + "x" * 500)

    failure = discord_sender._failure_from_exception(exc)

    assert "\n" not in failure.message
    assert failure.message.startswith("Discord returned an error (400): line one xxx")
    assert len(failure.message) <= len("Discord returned an error (400): ") + 200


def test_http_error_without_text_keeps_the_short_message():
    exc = http_error(discord.HTTPException, 500, "")

    failure = discord_sender._failure_from_exception(exc)

    assert failure.message == "Discord returned an error (500)"


def test_http_error_message_never_includes_headers_or_the_token():
    exc = http_error(discord.HTTPException, 400, "bad")
    exc.response.headers = {"Authorization": "Bot secret"}

    failure = discord_sender._failure_from_exception(exc)

    assert "secret" not in failure.message
    assert "Authorization" not in failure.message
