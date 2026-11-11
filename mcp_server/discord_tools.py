from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.concurrency import run_in_threadpool

from mcp_server import discord_sender, mongo
from mcp_server.config_path import DEFAULT_CONFIG_PATH
from mcp_server.discord_messages import MessageInvalidError, build_messages
from mcp_server.discord_sender import DiscordFailure, failure_result
from mcp_server.discord_settings import (
    DiscordSettingsInvalidError,
    DiscordSettingsStore,
    StoredDiscordSettings,
    is_snowflake,
    to_payload,
)
from scraper.config_loader import ConfigError

LOG = logging.getLogger(__name__)


def _discord_store() -> DiscordSettingsStore:
    return DiscordSettingsStore(mongo.get_database(), DEFAULT_CONFIG_PATH)


async def _with_discord(
    action: Callable[[StoredDiscordSettings], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    try:
        settings = await run_in_threadpool(_discord_store().read)
        return await action(settings)
    except DiscordFailure as exc:
        return exc.as_result()
    except MessageInvalidError as exc:
        return failure_result("invalid", str(exc))
    except ConfigError as exc:
        return failure_result("unavailable", str(exc))
    except Exception:
        LOG.exception("Discord request failed")
        return failure_result("unavailable", "Discord request failed")


def _require_discord_token(settings: StoredDiscordSettings) -> str:
    if not settings.token:
        raise DiscordFailure("not_configured", "Discord is not set up, save a bot token first")
    return settings.token


def get_discord_settings() -> dict[str, Any]:
    """Return the Discord settings, with the bot token masked.

    The token itself is never returned, only token_hint (for example "••••1234").
    message_template and max_chars fall back to the bot block of config.yaml
    until they are saved.

    Returns:
        {configured, token_hint, default_channel_id, mention_user_id,
        message_template, max_chars, updated_at}. configured is true when a
        token is saved. On failure: {error: str}.
    """
    try:
        return to_payload(_discord_store().read())
    except ConfigError as exc:
        return {"error": str(exc)}


def save_discord_settings(patch: dict[str, Any]) -> dict[str, Any]:
    """Change the Discord settings. Keys left out keep their current value.

    Args:
        patch: changes to apply. Allowed keys:
            token: non-empty string, replaces the saved token (it cannot be cleared)
            default_channel_id: 17 to 20 digit string, or null or "" to clear
            mention_user_id: 17 to 20 digit string, or null or "" to clear
            message_template: non-empty text with placeholders like {title},
                {company}, {location}, {url}; a missing field becomes empty text
            max_chars: whole number from 1 to 2000, the length one job message is cut to

    Returns:
        On success: {ok: True, settings} with the same shape as get_discord_settings.
        On failure: {ok: False, reason, message}. reason is "invalid" or "unavailable".
    """
    try:
        return {"ok": True, "settings": to_payload(_discord_store().save(patch))}
    except DiscordSettingsInvalidError as exc:
        return failure_result("invalid", str(exc))
    except ConfigError as exc:
        return failure_result("unavailable", str(exc))


async def test_discord_connection() -> dict[str, Any]:
    """Check that the saved bot token works, by logging in to Discord.

    Returns:
        On success: {ok: True, bot_name, bot_id}.
        On failure: {ok: False, reason, message}. reason is "not_configured",
        "unauthorized", or "unavailable".
    """

    async def action(settings: StoredDiscordSettings) -> dict[str, Any]:
        return await discord_sender.fetch_identity(_require_discord_token(settings))

    return await _with_discord(action)


async def list_discord_channels() -> dict[str, Any]:
    """List the text and announcement channels the bot can see.

    Channels are sorted by server name, then by their position in the server.

    Returns:
        On success: {ok: True, channels: [{id, name, guild_id, guild_name}]}.
        On failure: {ok: False, reason, message}. reason is "not_configured",
        "unauthorized", or "unavailable".
    """

    async def action(settings: StoredDiscordSettings) -> dict[str, Any]:
        return await discord_sender.fetch_channels(_require_discord_token(settings))

    return await _with_discord(action)


def preview_discord_message(
    mention: bool,
    text: str | None = None,
    jobs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the exact messages send_discord_message would post, without sending.

    Needs no token. Give exactly one of text or jobs. Jobs become one message
    each, filled into the saved message_template and cut to max_chars, then one
    short summary message. With mention true and a mention_user_id saved, the
    first message starts with a mention of that user.

    Args:
        mention: mention the saved user at the start of the first message.
        text: free text in markdown, up to 2000 characters including the mention.
        jobs: 1 to 50 job dicts, using the same field names as scrape_jobs results.

    Returns:
        On success: {ok: True, messages: [str]}.
        On failure: {ok: False, reason, message}. reason is "invalid" or "unavailable".
    """
    try:
        settings = _discord_store().read()
        messages = build_messages(settings, mention, text, jobs)
    except MessageInvalidError as exc:
        return failure_result("invalid", str(exc))
    except ConfigError as exc:
        return failure_result("unavailable", str(exc))
    return {"ok": True, "messages": [message.content for message in messages]}


async def send_discord_message(
    channel_id: str,
    mention: bool,
    text: str | None = None,
    jobs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Post a message to a Discord channel. Messages are sent one by one.

    Same content rules as preview_discord_message: give exactly one of text or
    jobs. Job sends end with a short summary message. One failed message does
    not stop the rest, unless Discord rejects the token. Only the saved user can
    be mentioned, never everyone or roles.

    Args:
        channel_id: 17 to 20 digit channel id.
        mention: mention the saved user at the start of the first message.
        text: free text in markdown, up to 2000 characters including the mention.
        jobs: 1 to 50 job dicts, using the same field names as scrape_jobs results.

    Returns:
        On success: {ok: True, sent, failed, results: [{index, kind, title,
        status, message_id, error}]}. index is the position in the message list
        from preview_discord_message, kind is "text", "job" or "summary", status
        is "sent" or "failed".
        On failure before sending: {ok: False, reason, message}. reason is
        "not_configured", "invalid", "unauthorized", "forbidden" (the bot cannot
        post in that channel), or "unavailable".
    """

    async def action(settings: StoredDiscordSettings) -> dict[str, Any]:
        token = _require_discord_token(settings)
        if not is_snowflake(channel_id):
            raise MessageInvalidError("channel_id must be a 17 to 20 digit string")
        messages = build_messages(settings, mention, text, jobs)
        return await discord_sender.post_messages(token, channel_id, messages)

    return await _with_discord(action)


DISCORD_TOOLS = (
    get_discord_settings,
    save_discord_settings,
    test_discord_connection,
    list_discord_channels,
    preview_discord_message,
    send_discord_message,
)
