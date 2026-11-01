from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
_DB_NAME = os.environ.get("MONGO_DB_NAME", "job_scraper")
_COLLECTION_NAME = os.environ.get("MONGO_COLLECTION_NAME", "scrape_runs")
# Bound server selection so a down/unreachable Mongo fails fast (default 30s)
# instead of stalling the /health probe past its curl timeout.
_SERVER_SELECTION_TIMEOUT_MS = int(os.environ.get("MONGO_SERVER_SELECTION_TIMEOUT_MS", "3000"))

_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is None:
        from pymongo import MongoClient  # deferred so import cost is zero when unused

        _client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=_SERVER_SELECTION_TIMEOUT_MS,
        )
    return _client


def get_database() -> Any:
    return _get_client()[_DB_NAME]


def get_collection() -> Any:
    return get_database()[_COLLECTION_NAME]


def ping() -> None:
    """Raise if MongoDB is unreachable, else return None.

    Uses the unauthenticated ``ping`` admin command: it verifies connectivity
    only, not credentials/authorization (matches the Mongo container's own
    healthcheck). A bad password still pings ok but would fail real queries.
    """
    _get_client().admin.command("ping")


def insert_run(data: dict[str, Any]) -> str:
    """Insert a scrape run document. Returns the inserted _id as a string."""
    collection = get_collection()
    doc = {**data, "_created_at": datetime.now(UTC).isoformat()}
    result = collection.insert_one(doc)
    return str(result.inserted_id)


def get_latest_run() -> dict[str, Any] | None:
    """Return the most recent scrape run document, or None if none exist."""
    collection = get_collection()
    doc = collection.find_one(sort=[("_created_at", -1)])
    if doc is None:
        return None
    return {**doc, "_id": str(doc["_id"])}


def update_run(run_id: str, patch: dict[str, Any]) -> bool:
    """Patch an existing scrape run document by _id. Returns True if a doc matched.

    Builds a new $set dict (injecting _updated_at) — never mutates ``patch``.
    Dot-notation keys (e.g. "run_metadata.bot_post_status") are honoured by MongoDB.
    """
    from bson import ObjectId

    collection = get_collection()
    set_doc = {**patch, "_updated_at": datetime.now(UTC).isoformat()}
    result = collection.update_one({"_id": ObjectId(run_id)}, {"$set": set_doc})
    return result.matched_count > 0
