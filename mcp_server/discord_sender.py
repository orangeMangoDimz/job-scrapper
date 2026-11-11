from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any

import aiohttp
import discord

from mcp_server.discord_messages import OutgoingMessage

UNAUTHORIZED_STATUS = 401
FORBIDDEN_STATUSES = (403, 404)
MAX_RATELIMIT_TIMEOUT_SECONDS = 30.0
SEND_DEADLINE_SECONDS = 150.0
ERROR_TEXT_LIMIT = 200
DEADLINE_ERROR = "Stopped: send took too long"
TOKEN_REJECTED_ERROR = "Stopped after Discord rejected the token"
NETWORK_ERRORS = (discord.DiscordException, aiohttp.ClientError, OSError, TimeoutError)


def failure_result(reason: str, message: str) -> dict[str, Any]:
    return {"ok": False, "reason": reason, "message": message}


class DiscordFailure(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message

    def as_result(self) -> dict[str, Any]:
        return failure_result(self.reason, self.message)


@dataclass(frozen=True)
class BotIdentity:
    name: str
    id: str


def _error_detail(exc: discord.HTTPException) -> str:
    text = " ".join(exc.text.split())[:ERROR_TEXT_LIMIT]
    return f": {text}" if text else ""


def _failure_from_exception(exc: Exception, *, channel: bool = False) -> DiscordFailure:
    if isinstance(exc, discord.LoginFailure):
        return DiscordFailure("unauthorized", "Discord rejected the bot token")
    if isinstance(exc, discord.HTTPException):
        if exc.status == UNAUTHORIZED_STATUS:
            return DiscordFailure("unauthorized", "Discord rejected the bot token")
        if channel and exc.status in FORBIDDEN_STATUSES:
            return DiscordFailure("forbidden", "The bot cannot post in that channel")
        return DiscordFailure(
            "unavailable", f"Discord returned an error ({exc.status}){_error_detail(exc)}"
        )
    if isinstance(exc, discord.RateLimited):
        return DiscordFailure(
            "unavailable", f"Discord rate limit hit, retry in {round(exc.retry_after)} seconds"
        )
    return DiscordFailure("unavailable", f"Discord cannot be reached ({type(exc).__name__})")


def _text_channel_row(guild: Any, channel: discord.TextChannel) -> dict[str, Any]:
    return {
        "id": str(channel.id),
        "name": channel.name,
        "guild_id": str(guild.id),
        "guild_name": guild.name,
        "position": channel.position,
    }


def _allowed_mentions(mention_user_id: str | None) -> discord.AllowedMentions:
    users: bool | list[discord.Object] = (
        [discord.Object(id=int(mention_user_id))] if mention_user_id else False
    )
    return discord.AllowedMentions(everyone=False, roles=False, users=users)


class DiscordRestClient:
    def __init__(self, token: str) -> None:
        self._token = token
        self._client = discord.Client(
            intents=discord.Intents.none(), max_ratelimit_timeout=MAX_RATELIMIT_TIMEOUT_SECONDS
        )
        self._channel: Any = None

    async def __aenter__(self) -> DiscordRestClient:
        try:
            await self._client.login(self._token)
        except NETWORK_ERRORS as exc:
            await self._client.close()
            raise _failure_from_exception(exc) from exc
        except BaseException:
            await self._client.close()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._client.close()

    async def identity(self) -> BotIdentity:
        user = self._client.user
        if user is None:
            raise DiscordFailure("unavailable", "Discord did not return the bot account")
        return BotIdentity(name=user.name, id=str(user.id))

    async def channels(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        try:
            async for guild in self._client.fetch_guilds(limit=None):
                guild_channels = await guild.fetch_channels()
                found.extend(
                    _text_channel_row(guild, channel)
                    for channel in guild_channels
                    if isinstance(channel, discord.TextChannel)
                )
        except NETWORK_ERRORS as exc:
            raise _failure_from_exception(exc) from exc
        return found

    async def check_channel(self, channel_id: str) -> None:
        try:
            channel = await self._client.fetch_channel(int(channel_id))
        except NETWORK_ERRORS as exc:
            raise _failure_from_exception(exc, channel=True) from exc
        if not hasattr(channel, "send"):
            raise DiscordFailure("forbidden", "The bot cannot post in that channel")
        self._channel = channel

    async def send(self, channel_id: str, content: str, mention_user_id: str | None = None) -> str:
        if self._channel is None:
            await self.check_channel(channel_id)
        try:
            message = await self._channel.send(
                content, allowed_mentions=_allowed_mentions(mention_user_id)
            )
        except NETWORK_ERRORS as exc:
            raise _failure_from_exception(exc, channel=True) from exc
        return str(message.id)


def open_client(token: str) -> DiscordRestClient:
    return DiscordRestClient(token)


async def fetch_identity(token: str) -> dict[str, Any]:
    async with open_client(token) as client:
        identity = await client.identity()
    return {"ok": True, "bot_name": identity.name, "bot_id": identity.id}


async def fetch_channels(token: str) -> dict[str, Any]:
    async with open_client(token) as client:
        found = await client.channels()
    ordered = sorted(
        found, key=lambda channel: (channel["guild_name"].casefold(), channel["position"])
    )
    return {
        "ok": True,
        "channels": [
            {key: channel[key] for key in ("id", "name", "guild_id", "guild_name")}
            for channel in ordered
        ],
    }


def _message_result(
    index: int,
    message: OutgoingMessage,
    message_id: str | None,
    error: str | None,
) -> dict[str, Any]:
    return {
        "index": index,
        "kind": message.kind,
        "title": message.title,
        "status": "failed" if error else "sent",
        "message_id": message_id,
        "error": error,
    }


async def _post_each(
    client: DiscordRestClient,
    channel_id: str,
    messages: Sequence[OutgoingMessage],
    results: list[dict[str, Any]],
) -> None:
    stopped = False
    for index, message in enumerate(messages):
        if stopped:
            results.append(_message_result(index, message, None, TOKEN_REJECTED_ERROR))
            continue
        try:
            message_id = await client.send(channel_id, message.content, message.mention_user_id)
        except DiscordFailure as exc:
            stopped = exc.reason == "unauthorized"
            results.append(_message_result(index, message, None, exc.message))
            continue
        results.append(_message_result(index, message, message_id, None))


async def post_messages(
    token: str, channel_id: str, messages: Sequence[OutgoingMessage]
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    async with open_client(token) as client:
        await client.check_channel(channel_id)
        try:
            async with asyncio.timeout(SEND_DEADLINE_SECONDS):
                await _post_each(client, channel_id, messages, results)
        except TimeoutError:
            start = len(results)
            results.extend(
                _message_result(index, message, None, DEADLINE_ERROR)
                for index, message in enumerate(messages[start:], start=start)
            )
    failed = sum(1 for entry in results if entry["status"] == "failed")
    return {"ok": True, "sent": len(results) - failed, "failed": failed, "results": results}
