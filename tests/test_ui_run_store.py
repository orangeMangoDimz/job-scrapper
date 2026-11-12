from __future__ import annotations

import json
from pathlib import Path

import pytest

from ui_server.errors import RunNotFoundError
from ui_server.services.run_store import (
    DISCORD_INTERRUPTED_MESSAGE,
    DiscordStatus,
    RunStatus,
    RunStore,
    build_payloads,
    flatten_result,
)


def _store(tmp_path: Path, keep_runs: int = 50) -> RunStore:
    return RunStore(tmp_path / "ui-runs", keep_runs)


def _result(ok: bool, count: int) -> dict:
    jobs = [{"title": f"job {index}"} for index in range(count)]
    return {
        "ok": ok,
        "results": [{"keyword": "django", "sites": [{"site": "upwork", "jobs": jobs}]}],
        "errors": [] if ok else [{"keyword": "django", "site": "indeed", "reason": "timeout"}],
    }


def test_create_writes_running_record(tmp_path: Path):
    store = _store(tmp_path)

    record = store.create(("django",), ("upwork",))

    assert record.status is RunStatus.RUNNING
    assert store.get(record.id) == record


def test_finish_saves_result_and_counts(tmp_path: Path):
    store = _store(tmp_path)
    record = store.create(("django",), ("upwork",))

    finished = store.finish(record, _result(True, 2))

    assert finished.status is RunStatus.SUCCEEDED
    assert finished.job_count == 2
    assert store.read_result(record.id)["ok"] is True


def test_finish_with_some_jobs_and_errors_is_partial(tmp_path: Path):
    store = _store(tmp_path)

    finished = store.finish(store.create(("django",), ("upwork",)), _result(False, 1))

    assert finished.status is RunStatus.PARTIAL
    assert finished.error_count == 1


def test_finish_with_no_jobs_and_errors_is_failed(tmp_path: Path):
    store = _store(tmp_path)

    finished = store.finish(store.create(("django",), ("upwork",)), _result(False, 0))

    assert finished.status is RunStatus.FAILED


def test_fail_keeps_message(tmp_path: Path):
    store = _store(tmp_path)

    failed = store.fail(store.create(("django",), ("upwork",)), "MCP down")

    assert failed.status is RunStatus.FAILED
    assert store.get(failed.id).error == "MCP down"


def test_get_rejects_unsafe_id(tmp_path: Path):
    with pytest.raises(RunNotFoundError):
        _store(tmp_path).get("../../etc")


def test_get_rejects_unknown_id(tmp_path: Path):
    with pytest.raises(RunNotFoundError):
        _store(tmp_path).get("20261101T120000Z-abcdef")


def test_list_recent_returns_newest_first(tmp_path: Path):
    store = _store(tmp_path)
    first = store.create(("a",), ("upwork",))
    second = store.create(("b",), ("upwork",))

    ids = [record.id for record in store.list_recent()]

    assert ids == sorted([first.id, second.id], reverse=True)


def test_prune_keeps_newest_runs(tmp_path: Path):
    store = _store(tmp_path, keep_runs=1)
    old = store.finish(store.create(("a",), ("upwork",)), _result(True, 0))
    new = store.finish(store.create(("b",), ("upwork",)), _result(True, 0))
    newest = max(old.id, new.id)

    store.prune()

    assert [record.id for record in store.list_recent()] == [newest]


def test_mark_interrupted_closes_running_runs(tmp_path: Path):
    store = _store(tmp_path)
    record = store.create(("a",), ("upwork",))

    store.mark_interrupted()

    assert store.get(record.id).status is RunStatus.INTERRUPTED


def test_update_discord_sets_fields_and_keeps_run_status(tmp_path: Path):
    store = _store(tmp_path)
    finished = store.finish(store.create(("django",), ("upwork",)), _result(True, 2))

    updated = store.update_discord(finished, DiscordStatus.PARTIAL, sent=3, failed=1, error="x")

    assert updated.status is RunStatus.SUCCEEDED
    assert store.get(finished.id) == updated
    assert (updated.discord_status, updated.discord_sent) == (DiscordStatus.PARTIAL, 3)
    assert (updated.discord_failed, updated.discord_error) == (1, "x")


def test_new_record_has_no_discord_fields(tmp_path: Path):
    record = _store(tmp_path).create(("django",), ("upwork",))

    assert record.discord_status is None
    assert (record.discord_sent, record.discord_failed, record.discord_error) == (0, 0, None)


def test_get_loads_record_saved_before_discord_fields(tmp_path: Path):
    store = _store(tmp_path)
    record = store.create(("a",), ("upwork",))
    path = tmp_path / "ui-runs" / record.id / "run.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    for name in ("discord_status", "discord_sent", "discord_failed", "discord_error"):
        del payload[name]
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert store.get(record.id).discord_status is None


def test_mark_interrupted_fails_sending_discord(tmp_path: Path):
    store = _store(tmp_path)
    finished = store.finish(store.create(("a",), ("upwork",)), _result(True, 1))
    sending = store.update_discord(finished, DiscordStatus.SENDING)

    store.mark_interrupted()

    reloaded = store.get(sending.id)
    assert reloaded.status is RunStatus.SUCCEEDED
    assert reloaded.discord_status is DiscordStatus.FAILED
    assert reloaded.discord_error == DISCORD_INTERRUPTED_MESSAGE


def test_mark_interrupted_keeps_sent_discord(tmp_path: Path):
    store = _store(tmp_path)
    finished = store.finish(store.create(("a",), ("upwork",)), _result(True, 1))
    sent = store.update_discord(finished, DiscordStatus.SENT, sent=1)

    store.mark_interrupted()

    assert store.get(sent.id) == sent


def _corrupt_record(tmp_path: Path, run_id: str) -> None:
    (tmp_path / "ui-runs" / run_id / "run.json").write_text("{broken")


def test_list_recent_skips_unreadable_record(tmp_path: Path):
    store = _store(tmp_path)
    good = store.create(("a",), ("upwork",))
    bad = store.create(("b",), ("upwork",))
    _corrupt_record(tmp_path, bad.id)

    assert [record.id for record in store.list_recent()] == [good.id]


def test_mark_interrupted_survives_unreadable_record(tmp_path: Path):
    store = _store(tmp_path)
    good = store.create(("a",), ("upwork",))
    bad = store.create(("b",), ("upwork",))
    _corrupt_record(tmp_path, bad.id)

    store.mark_interrupted()

    assert store.get(good.id).status is RunStatus.INTERRUPTED


def test_get_treats_unreadable_record_as_missing(tmp_path: Path):
    store = _store(tmp_path)
    record = store.create(("a",), ("upwork",))
    (tmp_path / "ui-runs" / record.id / "run.json").write_text("{}")

    with pytest.raises(RunNotFoundError):
        store.get(record.id)


def test_read_result_treats_unreadable_result_as_empty(tmp_path: Path):
    store = _store(tmp_path)
    record = store.create(("a",), ("upwork",))
    (tmp_path / "ui-runs" / record.id / "result.json").write_text("{broken")

    assert store.read_result(record.id) == {}


def test_flatten_result_returns_jobs_and_failures():
    jobs, failures = flatten_result(_result(False, 1))

    assert jobs == [{"title": "job 0"}]
    assert failures == [{"keyword": "django", "site": "indeed", "reason": "timeout"}]


def _payload_result() -> dict:
    return {
        "ok": True,
        "results": [],
        "errors": [],
        "raw_results": [
            {"keyword": "ai", "site": "glints", "payload": {"count": 5}},
            {"keyword": "ai", "site": "jobstreet", "payload": {"count": 4}},
            {"keyword": "ml", "site": "jobstreet", "payload": {"count": 2}},
        ],
        "filtered_results": [
            {"keyword": "ml", "site": "jobstreet", "payload": {"count": 1}},
            {"keyword": "ai", "site": "jobstreet", "payload": {"count": 3}},
        ],
    }


def test_build_payloads_pairs_raw_and_filtered_in_requested_order():
    payloads = build_payloads(_payload_result(), ("ai", "ml"), ("jobstreet", "glints"))

    assert payloads == [
        {"keyword": "ai", "site": "jobstreet", "raw": {"count": 4}, "filtered": {"count": 3}},
        {"keyword": "ai", "site": "glints", "raw": {"count": 5}, "filtered": None},
        {"keyword": "ml", "site": "jobstreet", "raw": {"count": 2}, "filtered": {"count": 1}},
    ]


def test_build_payloads_appends_stored_pairs_outside_the_record():
    result = {
        "raw_results": [
            {"keyword": "zz", "site": "indeed", "payload": {"count": 7}},
            {"keyword": "ai", "site": "jobstreet", "payload": {"count": 4}},
            {"keyword": "ml", "site": "glints", "payload": {"count": 6}},
        ],
        "filtered_results": [
            {"keyword": "ml", "site": "glints", "payload": {"count": 2}},
            {"keyword": "ai", "site": "linkedin", "payload": {"count": 1}},
        ],
    }

    payloads = build_payloads(result, ("ai",), ("jobstreet",))

    assert payloads == [
        {"keyword": "ai", "site": "jobstreet", "raw": {"count": 4}, "filtered": None},
        {"keyword": "zz", "site": "indeed", "raw": {"count": 7}, "filtered": None},
        {"keyword": "ml", "site": "glints", "raw": {"count": 6}, "filtered": {"count": 2}},
        {"keyword": "ai", "site": "linkedin", "raw": None, "filtered": {"count": 1}},
    ]


def test_build_payloads_is_empty_for_an_old_result():
    assert build_payloads({"ok": True, "results": []}, ("ai",), ("jobstreet",)) == []
    assert build_payloads({}, ("ai",), ("jobstreet",)) == []


def test_build_payloads_skips_malformed_entries():
    result = {
        "raw_results": [
            "junk",
            {"keyword": "ai"},
            {"keyword": "ai", "site": "jobstreet", "payload": "not an object"},
            {"keyword": "ai", "site": "glints", "payload": {"count": 1}},
            {"keyword": ["x"], "site": "glints", "payload": {"count": 9}},
        ],
        "filtered_results": {"not": "a list"},
    }

    payloads = build_payloads(result, ("ai",), ("jobstreet", "glints"))

    assert payloads == [{"keyword": "ai", "site": "glints", "raw": {"count": 1}, "filtered": None}]


def test_build_payloads_tolerates_non_list_sections():
    result = {"raw_results": None, "filtered_results": 5}

    assert build_payloads(result, ("ai",), ("jobstreet",)) == []


def test_read_result_ignores_a_result_file_that_is_not_an_object(tmp_path: Path):
    store = _store(tmp_path)
    record = store.create(("django",), ("upwork",))
    (tmp_path / "ui-runs" / record.id / "result.json").write_text("[1, 2]", encoding="utf-8")

    assert store.read_result(record.id) == {}
