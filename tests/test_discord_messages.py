from __future__ import annotations

from typing import Any

import pytest

from mcp_server.discord_messages import (
    MAX_JOBS,
    TEXT_LIMIT,
    MessageInvalidError,
    build_messages,
    render_job,
    summary_text,
    truncate,
)
from mcp_server.discord_settings import StoredDiscordSettings

USER_ID = "98765432109876543"
TEMPLATE = "## {title}\n{company} | {location}\n{url}"


def make_settings(**overrides: Any) -> StoredDiscordSettings:
    fields: dict[str, Any] = {
        "token": None,
        "default_channel_id": None,
        "mention_user_id": USER_ID,
        "message_template": TEMPLATE,
        "max_chars": 1900,
        "updated_at": None,
    }
    return StoredDiscordSettings(**{**fields, **overrides})


def make_job(index: int = 1, **overrides: Any) -> dict[str, Any]:
    return {
        "title": f"Job {index}",
        "company": "Acme",
        "location": "Jakarta",
        "url": f"https://example.com/{index}",
        **overrides,
    }


def test_render_job_fills_placeholders():
    assert render_job(TEMPLATE, make_job()) == ("## Job 1\nAcme | Jakarta\nhttps://example.com/1")


def test_render_job_turns_missing_and_null_fields_into_empty_text():
    job = {"title": "Only title", "company": None}

    assert render_job(TEMPLATE, job) == "## Only title\n | \n"


def test_render_job_leaves_unknown_braces_alone():
    assert render_job("{title} {x y} {0} } { {", {"title": "T"}) == "T {x y} {0} } { {"


def test_render_job_stringifies_numbers():
    assert render_job("{salary_min}", {"salary_min": 5000}) == "5000"


def test_render_job_does_not_expand_placeholders_inside_values():
    assert render_job("{title}", {"title": "{company}", "company": "Acme"}) == "{company}"


def test_truncate_keeps_short_content():
    assert truncate("abc", 3) == "abc"


def test_truncate_cuts_to_the_limit_with_an_ellipsis():
    cut = truncate("a" * 50, 10)

    assert len(cut) == 10
    assert cut.endswith("…")


def test_build_text_message():
    messages = build_messages(make_settings(), mention=False, text="hello **world**", jobs=None)

    assert [(m.kind, m.title, m.content) for m in messages] == [("text", None, "hello **world**")]


def test_build_text_message_with_mention_prefix():
    messages = build_messages(make_settings(), mention=True, text="hi", jobs=None)

    assert messages[0].content == f"<@{USER_ID}>\nhi"


def test_mention_is_ignored_when_no_user_is_saved():
    settings = make_settings(mention_user_id=None)

    messages = build_messages(settings, mention=True, text="hi", jobs=None)

    assert messages[0].content == "hi"


def test_text_limit_counts_the_mention_prefix():
    prefix_length = len(f"<@{USER_ID}>\n")

    build_messages(
        make_settings(), mention=True, text="a" * (TEXT_LIMIT - prefix_length), jobs=None
    )
    with pytest.raises(MessageInvalidError, match="2000"):
        build_messages(
            make_settings(), mention=True, text="a" * (TEXT_LIMIT - prefix_length + 1), jobs=None
        )


def test_text_of_exactly_the_limit_is_fine_without_mention():
    build_messages(make_settings(), mention=False, text="a" * TEXT_LIMIT, jobs=None)
    with pytest.raises(MessageInvalidError):
        build_messages(make_settings(), mention=False, text="a" * (TEXT_LIMIT + 1), jobs=None)


@pytest.mark.parametrize("text", ["", "   \n"])
def test_empty_text_is_invalid(text: str):
    with pytest.raises(MessageInvalidError, match="text"):
        build_messages(make_settings(), mention=False, text=text, jobs=None)


def test_text_that_is_not_a_string_is_invalid():
    with pytest.raises(MessageInvalidError):
        build_messages(make_settings(), mention=False, text=5, jobs=None)  # type: ignore[arg-type]


def test_both_text_and_jobs_is_invalid():
    with pytest.raises(MessageInvalidError, match="exactly one"):
        build_messages(make_settings(), mention=False, text="hi", jobs=[make_job()])


def test_neither_text_nor_jobs_is_invalid():
    with pytest.raises(MessageInvalidError, match="exactly one"):
        build_messages(make_settings(), mention=False, text=None, jobs=None)


def test_empty_jobs_list_is_invalid():
    with pytest.raises(MessageInvalidError, match="1"):
        build_messages(make_settings(), mention=False, text=None, jobs=[])


def test_too_many_jobs_is_invalid():
    jobs = [make_job(index) for index in range(MAX_JOBS + 1)]

    with pytest.raises(MessageInvalidError, match="50"):
        build_messages(make_settings(), mention=False, text=None, jobs=jobs)


def test_exactly_the_max_jobs_is_fine():
    jobs = [make_job(index) for index in range(MAX_JOBS)]

    messages = build_messages(make_settings(), mention=False, text=None, jobs=jobs)

    assert len(messages) == MAX_JOBS + 1


def test_jobs_that_are_not_mappings_are_invalid():
    with pytest.raises(MessageInvalidError, match="job"):
        build_messages(make_settings(), mention=False, text=None, jobs=["nope"])  # type: ignore[list-item]


def test_job_messages_use_the_template_then_a_summary():
    messages = build_messages(
        make_settings(), mention=False, text=None, jobs=[make_job(1), make_job(2)]
    )

    assert [m.kind for m in messages] == ["job", "job", "summary"]
    assert [m.title for m in messages] == ["Job 1", "Job 2", None]
    assert messages[0].content == "## Job 1\nAcme | Jakarta\nhttps://example.com/1"
    assert messages[2].content == summary_text(2)


def test_job_title_is_none_when_the_job_has_no_title():
    messages = build_messages(make_settings(), mention=False, text=None, jobs=[{"company": "A"}])

    assert messages[0].title is None


def test_job_messages_are_truncated_to_max_chars():
    settings = make_settings(max_chars=40, message_template="{title}")

    messages = build_messages(settings, mention=False, text=None, jobs=[make_job(title="x" * 200)])

    assert len(messages[0].content) == 40
    assert messages[0].content.endswith("…")


def test_mention_only_prefixes_the_first_message():
    messages = build_messages(
        make_settings(), mention=True, text=None, jobs=[make_job(1), make_job(2)]
    )

    assert messages[0].content.startswith(f"<@{USER_ID}>\n## Job 1")
    assert not messages[1].content.startswith("<@")
    assert "<@" not in messages[2].content


def test_first_job_message_with_mention_still_fits_max_chars():
    settings = make_settings(max_chars=60, message_template="{title}")

    messages = build_messages(
        settings, mention=True, text=None, jobs=[make_job(title="x" * 200), make_job(2)]
    )

    assert len(messages[0].content) == 60
    assert messages[0].content.startswith(f"<@{USER_ID}>\n")


def test_summary_text_is_short_and_counts_jobs():
    assert summary_text(3) == "Total: 3 job(s)"


def test_mention_is_never_cut_when_max_chars_is_small():
    settings = make_settings(max_chars=10, message_template="{title}")

    messages = build_messages(
        settings, mention=True, text=None, jobs=[make_job(title="x" * 200), make_job(2)]
    )

    assert messages[0].content == f"<@{USER_ID}>\n"
    assert messages[1].content.startswith("Job 2")


def test_job_body_is_cut_so_the_mention_and_body_fit_max_chars():
    prefix = f"<@{USER_ID}>\n"
    settings = make_settings(max_chars=len(prefix) + 5, message_template="{title}")

    messages = build_messages(settings, mention=True, text=None, jobs=[make_job(title="x" * 200)])

    assert messages[0].content == prefix + "xxxx…"


def test_first_job_message_never_exceeds_the_discord_limit():
    settings = make_settings(max_chars=TEXT_LIMIT, message_template="{title}")

    messages = build_messages(settings, mention=True, text=None, jobs=[make_job(title="x" * 5000)])

    assert len(messages[0].content) <= TEXT_LIMIT
    assert messages[0].content.startswith(f"<@{USER_ID}>\n")


def test_only_the_prefixed_message_carries_the_mention_user_id():
    messages = build_messages(
        make_settings(), mention=True, text=None, jobs=[make_job(1), make_job(2)]
    )

    assert [message.mention_user_id for message in messages] == [USER_ID, None, None]


def test_text_message_carries_the_mention_user_id():
    messages = build_messages(make_settings(), mention=True, text="hi", jobs=None)

    assert messages[0].mention_user_id == USER_ID


def test_no_message_carries_a_mention_user_id_when_mention_is_off():
    messages = build_messages(
        make_settings(), mention=False, text=None, jobs=[make_job(1), make_job(2)]
    )

    assert [message.mention_user_id for message in messages] == [None, None, None]


def test_no_message_carries_a_mention_user_id_when_no_user_is_saved():
    messages = build_messages(
        make_settings(mention_user_id=None), mention=True, text=None, jobs=[make_job(1)]
    )

    assert [message.mention_user_id for message in messages] == [None, None]


def test_a_job_title_with_a_mention_never_sets_the_mention_user_id():
    job = make_job(1, title="<@123456789012345678>")

    messages = build_messages(make_settings(), mention=False, text=None, jobs=[job])

    assert messages[0].mention_user_id is None
