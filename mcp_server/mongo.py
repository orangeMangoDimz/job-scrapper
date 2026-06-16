from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from scraper import settings

_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is None:
        from pymongo import MongoClient  # deferred so import cost is zero when unused

        _client = MongoClient(
            settings.MONGO_URI,
            serverSelectionTimeoutMS=settings.MONGO_SERVER_SELECTION_TIMEOUT_MS,
        )
    return _client


def get_collection() -> Any:
    return _get_client()[settings.MONGO_DB_NAME][settings.MONGO_COLLECTION_NAME]


def close() -> None:
    """Close the shared client and reset it (graceful shutdown). Idempotent."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


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
