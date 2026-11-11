from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import mongomock
import pytest
from pymongo.errors import ServerSelectionTimeoutError

from mcp_server.discord_settings import (
    DEFAULT_MAX_CHARS,
    DEFAULT_MESSAGE_TEMPLATE,
    DISCORD_COLLECTION,
    DISCORD_ID,
    DiscordSettingsInvalidError,
    DiscordSettingsStore,
    DiscordSettingsUnavailableError,
    is_snowflake,
    to_payload,
)

CHANNEL_ID = "123456789012345678"
USER_ID = "98765432109876543"
TOKEN = "abc.def.secret-token-1234"
CONFIG_YAML = """\
bot:
  max_chars: 1500
  message_template: |
    ## {title}
    {company}
"""


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG_YAML)
    return path


@pytest.fixture
def database() -> Any:
    return mongomock.MongoClient()["job_scraper"]


@pytest.fixture
def store(database: Any, config_path: Path) -> DiscordSettingsStore:
    return DiscordSettingsStore(database, config_path)


def test_read_without_saved_settings_uses_config_defaults(store: DiscordSettingsStore):
    settings = store.read()

    assert settings.token is None
    assert settings.default_channel_id is None
    assert settings.mention_user_id is None
    assert settings.message_template == "## {title}\n{company}\n"
    assert settings.max_chars == 1500
    assert settings.updated_at is None


def test_read_falls_back_when_config_has_no_bot_block(database: Any, tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("concurrency: 2\n")

    settings = DiscordSettingsStore(database, path).read()

    assert settings.message_template == DEFAULT_MESSAGE_TEMPLATE
    assert settings.max_chars == DEFAULT_MAX_CHARS == 1900


def test_read_falls_back_when_config_file_is_missing(database: Any, tmp_path: Path):
    settings = DiscordSettingsStore(database, tmp_path / "missing.yaml").read()

    assert settings.message_template == DEFAULT_MESSAGE_TEMPLATE
    assert settings.max_chars == DEFAULT_MAX_CHARS


def test_read_falls_back_when_config_is_not_valid_yaml(database: Any, tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("bot: [unclosed\n")

    settings = DiscordSettingsStore(database, path).read()

    assert settings.message_template == DEFAULT_MESSAGE_TEMPLATE
    assert settings.max_chars == DEFAULT_MAX_CHARS


def test_read_falls_back_when_bot_values_are_unusable(database: Any, tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("bot:\n  max_chars: lots\n  message_template: 5\n")

    settings = DiscordSettingsStore(database, path).read()

    assert settings.message_template == DEFAULT_MESSAGE_TEMPLATE
    assert settings.max_chars == DEFAULT_MAX_CHARS


def test_save_stores_everything_in_its_own_document(store: DiscordSettingsStore, database: Any):
    store.save(
        {
            "token": TOKEN,
            "default_channel_id": CHANNEL_ID,
            "mention_user_id": USER_ID,
            "message_template": "{title}",
            "max_chars": 1000,
        }
    )

    document = database[DISCORD_COLLECTION].find_one({"_id": DISCORD_ID})
    assert document["token"] == TOKEN
    assert document["default_channel_id"] == CHANNEL_ID
    assert document["mention_user_id"] == USER_ID
    assert document["message_template"] == "{title}"
    assert document["max_chars"] == 1000
    assert database[DISCORD_COLLECTION].count_documents({}) == 1
    assert "job_settings" not in database.list_collection_names()


def test_save_returns_the_new_settings_with_a_timestamp(store: DiscordSettingsStore):
    settings = store.save({"token": TOKEN})

    assert settings.token == TOKEN
    assert settings.updated_at is not None
    assert settings.updated_at.endswith("+00:00")


def test_save_keeps_omitted_keys(store: DiscordSettingsStore):
    store.save({"token": TOKEN, "default_channel_id": CHANNEL_ID, "max_chars": 800})

    settings = store.save({"mention_user_id": USER_ID})

    assert settings.token == TOKEN
    assert settings.default_channel_id == CHANNEL_ID
    assert settings.mention_user_id == USER_ID
    assert settings.max_chars == 800


def test_save_empty_patch_changes_nothing(store: DiscordSettingsStore):
    store.save({"token": TOKEN})

    settings = store.save({})

    assert settings.token == TOKEN


@pytest.mark.parametrize("key", ["default_channel_id", "mention_user_id"])
@pytest.mark.parametrize("cleared", [None, ""])
def test_save_clears_ids_with_null_or_empty(store: DiscordSettingsStore, key: str, cleared: Any):
    store.save({"token": TOKEN, "default_channel_id": CHANNEL_ID, "mention_user_id": USER_ID})

    settings = store.save({key: cleared})

    assert getattr(settings, key) is None
    assert settings.token == TOKEN


def test_save_rejects_unknown_key(store: DiscordSettingsStore):
    with pytest.raises(DiscordSettingsInvalidError, match="webhook"):
        store.save({"webhook": "x"})


def test_save_rejects_a_patch_that_is_not_a_mapping(store: DiscordSettingsStore):
    with pytest.raises(DiscordSettingsInvalidError):
        store.save(["token"])  # type: ignore[arg-type]


@pytest.mark.parametrize("token", ["", "   ", None, 5])
def test_save_rejects_empty_or_non_text_token(store: DiscordSettingsStore, token: Any):
    store.save({"token": TOKEN})

    with pytest.raises(DiscordSettingsInvalidError, match="token"):
        store.save({"token": token})

    assert store.read().token == TOKEN


@pytest.mark.parametrize(
    "token",
    ["abc def", "abc\ndef", "abc\tdef", "abc\u00a0def", "abc/def", "abc:def", "tok€n", "a b\n"],
)
def test_save_rejects_a_token_with_whitespace_or_odd_characters(
    store: DiscordSettingsStore, token: str
):
    store.save({"token": TOKEN})

    with pytest.raises(DiscordSettingsInvalidError, match="token") as caught:
        store.save({"token": token})

    assert str(caught.value) == "token must not contain spaces, line breaks, or other symbols"
    assert store.read().token == TOKEN


def test_save_accepts_the_characters_of_a_real_token(store: DiscordSettingsStore):
    token = "MTA.Gx_-aB.0123456789-_abcXYZ"

    assert store.save({"token": f" {token} "}).token == token


def test_stored_settings_repr_never_includes_the_token(store: DiscordSettingsStore):
    settings = store.save({"token": TOKEN})

    assert TOKEN not in repr(settings)
    assert "token=" not in repr(settings)


def test_save_trims_the_token(store: DiscordSettingsStore):
    assert store.save({"token": f"  {TOKEN}\n"}).token == TOKEN


@pytest.mark.parametrize(
    "value", ["1234", "1" * 16, "1" * 21, "12345678901234567a", 123456789012345678, " ", "<#1>"]
)
@pytest.mark.parametrize("key", ["default_channel_id", "mention_user_id"])
def test_save_rejects_bad_ids(store: DiscordSettingsStore, key: str, value: Any):
    with pytest.raises(DiscordSettingsInvalidError, match=key):
        store.save({key: value})


@pytest.mark.parametrize("value", ["1" * 17, "1" * 20])
def test_save_accepts_id_length_limits(store: DiscordSettingsStore, value: str):
    assert store.save({"default_channel_id": value}).default_channel_id == value


@pytest.mark.parametrize("value", ["", "   ", None, 5])
def test_save_rejects_empty_or_non_text_template(store: DiscordSettingsStore, value: Any):
    with pytest.raises(DiscordSettingsInvalidError, match="message_template"):
        store.save({"message_template": value})


@pytest.mark.parametrize("value", [0, -1, 2001, "1000", 1.5, True, None])
def test_save_rejects_bad_max_chars(store: DiscordSettingsStore, value: Any):
    with pytest.raises(DiscordSettingsInvalidError, match="max_chars"):
        store.save({"max_chars": value})


@pytest.mark.parametrize("value", [1, 2000])
def test_save_accepts_max_chars_limits(store: DiscordSettingsStore, value: int):
    assert store.save({"max_chars": value}).max_chars == value


def test_invalid_patch_writes_nothing(store: DiscordSettingsStore, database: Any):
    with pytest.raises(DiscordSettingsInvalidError):
        store.save({"token": TOKEN, "max_chars": 5000})

    assert database[DISCORD_COLLECTION].count_documents({}) == 0


def test_mongo_failure_on_read_hides_connection_details():
    database = MagicMock()
    database.__getitem__.return_value.find_one.side_effect = ServerSelectionTimeoutError(
        "secret-host:27017"
    )

    with pytest.raises(DiscordSettingsUnavailableError) as caught:
        DiscordSettingsStore(database, Path("config.yaml")).read()

    assert "secret-host" not in str(caught.value)


def test_mongo_failure_on_save_is_unavailable():
    database = MagicMock()
    database.__getitem__.return_value.update_one.side_effect = ServerSelectionTimeoutError("down")

    with pytest.raises(DiscordSettingsUnavailableError):
        DiscordSettingsStore(database, Path("config.yaml")).save({"token": TOKEN})


def test_payload_when_nothing_is_saved(store: DiscordSettingsStore):
    assert to_payload(store.read()) == {
        "configured": False,
        "token_hint": None,
        "default_channel_id": None,
        "mention_user_id": None,
        "message_template": "## {title}\n{company}\n",
        "max_chars": 1500,
        "updated_at": None,
    }


def test_payload_masks_the_token(store: DiscordSettingsStore):
    store.save({"token": TOKEN, "default_channel_id": CHANNEL_ID})

    payload = to_payload(store.read())

    assert payload["configured"] is True
    assert payload["token_hint"] == "••••1234"
    assert payload["default_channel_id"] == CHANNEL_ID
    assert TOKEN not in str(payload)
    assert "token" not in payload


def test_payload_masks_a_short_token_without_revealing_it(store: DiscordSettingsStore):
    store.save({"token": "ab"})

    assert to_payload(store.read())["token_hint"] == "••••"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1" * 17, True),
        ("1" * 20, True),
        ("1" * 16, False),
        ("1" * 21, False),
        ("a" * 18, False),
        ("١" * 18, False),
        ("1" * 17 + "\n", False),
    ],
)
def test_is_snowflake(value: str, expected: bool):
    assert is_snowflake(value) is expected


def test_is_snowflake_rejects_non_text():
    assert is_snowflake(123456789012345678) is False
    assert is_snowflake(None) is False
