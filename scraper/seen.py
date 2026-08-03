from __future__ import annotations

import os
import threading
from datetime import UTC, datetime
from typing import Any

from .log import get_logger
from .types import Job

_LOG = get_logger()

_SEEN_COLLECTION = "seen_jobs"


def _connect() -> Any | None:
    """Return the ``seen_jobs`` collection, or None if Mongo is unavailable.

    Mirrors scraper/sites/_location.py: the scraper package talks to Mongo
    directly (same env vars) so runner.run stays self-contained. Fails soft —
    a None collection means cross-run dedup is disabled, never a crash."""
    try:
        from pymongo import MongoClient
    except ImportError:
        _LOG.warning("[seen] pymongo unavailable; cross-run dedup disabled")
        return None

    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB_NAME", "job_scraper")
    timeout = int(os.environ.get("MONGO_SERVER_SELECTION_TIMEOUT_MS", "3000"))
    try:
        client: Any = MongoClient(uri, serverSelectionTimeoutMS=timeout)
        return client[db_name][_SEEN_COLLECTION]
    except Exception as exc:  # noqa: BLE001 - fail soft by design
        _LOG.warning("[seen] mongo connect failed (%s); cross-run dedup disabled", exc)
        return None


def seen_record(key: str, job: Job) -> dict[str, Any]:
    """Build the persisted document for a newly-seen job."""
    return {
        "dedup_key": key,
        "site": job.get("site"),
        "job_id": job.get("job_id"),
        "url": job.get("url"),
        "title": job.get("title"),
        "company": job.get("company"),
        "first_seen_at": datetime.now(UTC).isoformat(),
    }


class SeenStore:
    """Cross-run dedup of scraped jobs.

    Backed by the Mongo ``seen_jobs`` collection (unique index on ``dedup_key``),
    plus a thread-safe in-run set so concurrently-scraped (keyword, site) pairs
    don't each re-emit the same posting within one run. Fails soft: if Mongo is
    unreachable, every job is treated as new (favours reposting over silence).

    Pass ``use_mongo=False`` for in-run-only dedup with no persistence (used as
    the default when no store is injected, e.g. the CLI unit path).
    """

    def __init__(self, use_mongo: bool = True) -> None:
        self._lock = threading.Lock()
        self._in_run: set[str] = set()
        # Any (not Any | None) so mypy doesn't flag the guarded pymongo calls;
        # None still means "Mongo unavailable / disabled" at runtime.
        self._collection: Any = _connect() if use_mongo else None
        if self._collection is not None:
            self._ensure_index()

    def _ensure_index(self) -> None:
        try:
            self._collection.create_index("dedup_key", unique=True)
        except Exception as exc:  # noqa: BLE001 - fail soft
            _LOG.warning("[seen] create_index failed (%s); cross-run dedup degraded", exc)

    def is_seen(self, key: str) -> bool:
        with self._lock:
            if key in self._in_run:
                return True
        if self._collection is None:
            return False
        try:
            return self._collection.find_one({"dedup_key": key}, {"_id": 1}) is not None
        except Exception as exc:  # noqa: BLE001 - fail soft
            _LOG.warning("[seen] lookup failed for %r (%s); treating as new", key, exc)
            return False

    def remember_in_run(self, key: str) -> None:
        with self._lock:
            self._in_run.add(key)

    def mark_seen(self, records: list[dict[str, Any]]) -> None:
        if self._collection is None or not records:
            return
        try:
            from pymongo import UpdateOne

            ops = [
                UpdateOne({"dedup_key": r["dedup_key"]}, {"$setOnInsert": r}, upsert=True)
                for r in records
            ]
            self._collection.bulk_write(ops, ordered=False)
        except Exception as exc:  # noqa: BLE001 - fail soft
            _LOG.warning("[seen] mark_seen failed (%s); %d job(s) not persisted", exc, len(records))
