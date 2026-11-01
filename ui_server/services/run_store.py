from __future__ import annotations

import json
import logging
import re
import secrets
import shutil
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from ui_server.errors import RunNotFoundError

LOG = logging.getLogger("scraper-ui")
RUN_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{6}$")
RECORD_FILE = "run.json"
RESULT_FILE = "result.json"
INTERRUPTED_MESSAGE = "The UI service restarted during this run."
UNREADABLE_ERRORS = (OSError, ValueError, KeyError, TypeError)


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class RunRecord:
    id: str
    status: RunStatus
    keywords: tuple[str, ...]
    sites: tuple[str, ...]
    started_at: str
    finished_at: str | None = None
    job_count: int = 0
    error_count: int = 0
    error: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _new_run_id() -> str:
    return f"{_now():%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _to_record(payload: dict[str, Any]) -> RunRecord:
    return RunRecord(
        **{
            **payload,
            "status": RunStatus(payload["status"]),
            "keywords": tuple(payload["keywords"]),
            "sites": tuple(payload["sites"]),
        }
    )


def flatten_result(
    result: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    jobs = [
        job
        for group in result.get("results", [])
        for site in group.get("sites", [])
        for job in site.get("jobs", [])
    ]
    return jobs, list(result.get("errors", []))


def _status_for(result: dict[str, Any], job_count: int) -> RunStatus:
    if result.get("ok"):
        return RunStatus.SUCCEEDED
    return RunStatus.PARTIAL if job_count > 0 else RunStatus.FAILED


class RunStore:
    def __init__(self, root: Path, keep_runs: int) -> None:
        self._root = root
        self._keep_runs = keep_runs

    def create(self, keywords: tuple[str, ...], sites: tuple[str, ...]) -> RunRecord:
        record = RunRecord(
            id=_new_run_id(),
            status=RunStatus.RUNNING,
            keywords=keywords,
            sites=sites,
            started_at=_now().isoformat(),
        )
        self._run_dir(record.id).mkdir(parents=True)
        self._save(record)
        return record

    def finish(self, record: RunRecord, result: dict[str, Any]) -> RunRecord:
        jobs, failures = flatten_result(result)
        _write_json(self._run_dir(record.id) / RESULT_FILE, result)
        return self._save(
            replace(
                record,
                status=_status_for(result, len(jobs)),
                finished_at=_now().isoformat(),
                job_count=len(jobs),
                error_count=len(failures),
            )
        )

    def fail(self, record: RunRecord, message: str) -> RunRecord:
        return self._save(
            replace(
                record,
                status=RunStatus.FAILED,
                finished_at=_now().isoformat(),
                error=message,
            )
        )

    def get(self, run_id: str) -> RunRecord:
        path = self._record_path(run_id)
        if not path.exists():
            raise RunNotFoundError()
        try:
            return _to_record(json.loads(path.read_text(encoding="utf-8")))
        except UNREADABLE_ERRORS as exc:
            LOG.warning("unreadable run record %s: %s", run_id, exc)
            raise RunNotFoundError() from exc

    def read_result(self, run_id: str) -> dict[str, Any]:
        path = self._record_path(run_id).with_name(RESULT_FILE)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except UNREADABLE_ERRORS as exc:
            LOG.warning("unreadable run result %s: %s", run_id, exc)
            return {}

    def list_recent(self) -> tuple[RunRecord, ...]:
        records = (self._read_or_none(run_id) for run_id in reversed(self._run_ids()))
        return tuple(record for record in records if record is not None)

    def mark_interrupted(self) -> None:
        for record in self.list_recent():
            if record.status is RunStatus.RUNNING:
                self._save(
                    replace(
                        record,
                        status=RunStatus.INTERRUPTED,
                        finished_at=_now().isoformat(),
                        error=INTERRUPTED_MESSAGE,
                    )
                )

    def prune(self) -> None:
        run_ids = self._run_ids()
        for run_id in run_ids[: max(len(run_ids) - self._keep_runs, 0)]:
            shutil.rmtree(self._run_dir(run_id))
            LOG.info("removed old run folder %s", run_id)

    def _read_or_none(self, run_id: str) -> RunRecord | None:
        try:
            return self.get(run_id)
        except RunNotFoundError:
            return None

    def _run_ids(self) -> list[str]:
        if not self._root.exists():
            return []
        return sorted(
            path.name
            for path in self._root.iterdir()
            if RUN_ID_PATTERN.match(path.name) and (path / RECORD_FILE).exists()
        )

    def _run_dir(self, run_id: str) -> Path:
        return self._root / run_id

    def _record_path(self, run_id: str) -> Path:
        if not RUN_ID_PATTERN.match(run_id):
            raise RunNotFoundError()
        return self._run_dir(run_id) / RECORD_FILE

    def _save(self, record: RunRecord) -> RunRecord:
        _write_json(self._run_dir(record.id) / RECORD_FILE, asdict(record))
        return record
