from __future__ import annotations

from pathlib import Path

import pytest

from ui_server.errors import RunNotFoundError
from ui_server.services.run_store import RunStatus, RunStore, flatten_result


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


def test_flatten_result_returns_jobs_and_failures():
    jobs, failures = flatten_result(_result(False, 1))

    assert jobs == [{"title": "job 0"}]
    assert failures == [{"keyword": "django", "site": "indeed", "reason": "timeout"}]
