from __future__ import annotations

import pytest
from pydantic import ValidationError

from ui_server.schema.discord import (
    DiscordMessageRequest,
    DiscordSendRequest,
    DiscordSettingsRequest,
)

CHANNEL_ID = "123456789012345678"
RUN_ID = "20261101T010000Z-abc123"


def test_message_request_accepts_text():
    request = DiscordMessageRequest(mention=True, text="hello")

    assert request.text == "hello"
    assert request.job_indexes is None


def test_message_request_accepts_run_jobs():
    request = DiscordMessageRequest(mention=False, run_id=RUN_ID, job_indexes=[0, 2])

    assert request.job_indexes == [0, 2]


@pytest.mark.parametrize(
    "body",
    [
        {"mention": True},
        {"mention": True, "text": "hi", "run_id": RUN_ID, "job_indexes": [0]},
        {"mention": True, "text": "hi", "job_indexes": [0]},
        {"mention": True, "run_id": RUN_ID},
        {"mention": True, "job_indexes": [0]},
        {"mention": True, "text": ""},
        {"mention": True, "text": "x" * 2001},
        {"mention": True, "run_id": RUN_ID, "job_indexes": []},
        {"mention": True, "run_id": RUN_ID, "job_indexes": [1, 1]},
        {"mention": True, "run_id": RUN_ID, "job_indexes": [-1]},
        {"mention": True, "run_id": RUN_ID, "job_indexes": list(range(51))},
        {"mention": True, "run_id": RUN_ID, "job_indexes": ["a"]},
        {"text": "hi"},
        {"mention": True, "text": "hi", "extra": 1},
    ],
)
def test_message_request_rejects_bad_body(body: dict):
    with pytest.raises(ValidationError):
        DiscordMessageRequest(**body)


def test_message_request_accepts_fifty_jobs():
    request = DiscordMessageRequest(mention=True, run_id=RUN_ID, job_indexes=list(range(50)))

    assert len(request.job_indexes or []) == 50


def test_send_request_needs_channel_id():
    with pytest.raises(ValidationError):
        DiscordSendRequest.model_validate({"mention": True, "text": "hi"})


@pytest.mark.parametrize(
    "channel_id", ["1" * 16, "1" * 21, "12345678901234567a", "", " " * 18, "\u0661" * 18]
)
def test_send_request_rejects_bad_channel_id(channel_id: str):
    with pytest.raises(ValidationError):
        DiscordSendRequest(channel_id=channel_id, mention=True, text="hi")


@pytest.mark.parametrize("channel_id", ["1" * 17, "1" * 20])
def test_send_request_accepts_channel_id_bounds(channel_id: str):
    assert (
        DiscordSendRequest(channel_id=channel_id, mention=True, text="hi").channel_id == channel_id
    )


def test_settings_request_patch_keeps_only_sent_fields():
    request = DiscordSettingsRequest(max_chars=1500)

    assert request.to_patch() == {"max_chars": 1500}


def test_settings_request_patch_keeps_explicit_clears():
    request = DiscordSettingsRequest(default_channel_id=None, mention_user_id="")

    assert request.to_patch() == {"default_channel_id": None, "mention_user_id": ""}


def test_settings_request_accepts_full_body():
    request = DiscordSettingsRequest(
        token="abc.def",
        default_channel_id=CHANNEL_ID,
        mention_user_id=CHANNEL_ID,
        message_template="{title}",
        max_chars=2000,
    )

    assert request.to_patch()["token"] == "abc.def"


@pytest.mark.parametrize(
    "body",
    [
        {"token": ""},
        {"token": "   "},
        {"token": "abc\ndef"},
        {"token": "abc def"},
        {"token": None},
        {"default_channel_id": "123"},
        {"mention_user_id": "x" * 18},
        {"message_template": ""},
        {"message_template": None},
        {"max_chars": 0},
        {"max_chars": 2001},
        {"max_chars": None},
        {"unknown": "x"},
    ],
)
def test_settings_request_rejects_bad_body(body: dict):
    with pytest.raises(ValidationError):
        DiscordSettingsRequest(**body)
