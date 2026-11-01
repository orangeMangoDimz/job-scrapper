from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pymongo import DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from .config_loader import (
    AppConfig,
    ConfigError,
    parse,
    read_machine_settings,
    resolve_proxy_url,
    validate_job_settings,
)

SETTINGS_COLLECTION = "job_settings"
HISTORY_COLLECTION = "job_settings_history"
SETTINGS_ID = "active"
KEEP_HISTORY = 20
SOURCE_SEED = "seed"
FIRST_VERSION = 1
CONFLICT_MESSAGE = "These settings changed somewhere else. Reload and try again"


class SettingsMissingError(ConfigError):
    pass


class SettingsConflictError(ConfigError):
    pass


class SettingsUnavailableError(ConfigError):
    pass


@dataclass(frozen=True)
class StoredSettings:
    version: int
    settings: dict[str, Any]
    updated_at: str
    updated_by: str


def _to_stored(document: dict[str, Any]) -> StoredSettings:
    return StoredSettings(
        version=document["version"],
        settings=document["settings"],
        updated_at=document["updated_at"],
        updated_by=document["updated_by"],
    )


def _stamp(settings: dict[str, Any], version: int, source: str) -> dict[str, Any]:
    return {
        "version": version,
        "settings": settings,
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": source,
    }


def _apply_fields(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    kept = {key: value for key, value in current.items() if key not in patch}
    changed = {key: value for key, value in patch.items() if value is not None}
    return {**kept, **changed}


def _merge_site(current: dict[str, Any], name: str, patch: Any) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise ConfigError(f"sites.{name} must be a mapping")
    return _apply_fields(current.get(name, {}), patch)


def merge_settings(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = _apply_fields(current, {k: v for k, v in patch.items() if k != "sites"})
    site_patches = patch.get("sites")
    if site_patches is None:
        return merged
    if not isinstance(site_patches, dict):
        raise ConfigError("'sites' must be a mapping")
    sites = current.get("sites", {})
    changed = {name: _merge_site(sites, name, fields) for name, fields in site_patches.items()}
    return {**merged, "sites": {**sites, **changed}}


@contextmanager
def _mongo_errors() -> Iterator[None]:
    try:
        yield
    except PyMongoError as exc:
        # Keep the message short: pymongo errors can name hosts
        raise SettingsUnavailableError(
            f"The job settings store cannot be reached ({type(exc).__name__})"
        ) from exc


class JobSettingsStore:
    def __init__(self, database: Any) -> None:
        self._settings = database[SETTINGS_COLLECTION]
        self._history = database[HISTORY_COLLECTION]

    def read(self) -> StoredSettings:
        with _mongo_errors():
            document = self._settings.find_one({"_id": SETTINGS_ID})
        if document is None:
            raise SettingsMissingError(
                "Job settings are missing. Run ./seed.sh job-settings for this environment"
            )
        return _to_stored(document)

    def seed(self, settings: dict[str, Any]) -> bool:
        validate_job_settings(settings)
        document = {"_id": SETTINGS_ID, **_stamp(settings, FIRST_VERSION, SOURCE_SEED)}
        with _mongo_errors():
            try:
                self._settings.insert_one(document)
            except DuplicateKeyError:
                return False
        return True

    def save(
        self, patch: dict[str, Any], expected_version: int | None, source: str
    ) -> StoredSettings:
        current = self._read_expected(expected_version)
        return self._replace(current, merge_settings(current.settings, patch), source)

    def restore(self, version: int, expected_version: int, source: str) -> StoredSettings:
        current = self._read_expected(expected_version)
        with _mongo_errors():
            entry = self._history.find_one({"version": version})
        if entry is None:
            raise ConfigError(f"no saved version {version}")
        return self._replace(current, entry["settings"], source)

    def history(self) -> tuple[StoredSettings, ...]:
        with _mongo_errors():
            documents = list(self._history.find().sort("version", DESCENDING).limit(KEEP_HISTORY))
        return tuple(_to_stored(document) for document in documents)

    def _read_expected(self, expected_version: int | None) -> StoredSettings:
        current = self.read()
        if expected_version is not None and expected_version != current.version:
            raise SettingsConflictError(CONFLICT_MESSAGE)
        return current

    def _replace(
        self, current: StoredSettings, settings: dict[str, Any], source: str
    ) -> StoredSettings:
        validate_job_settings(settings)
        fields = _stamp(settings, current.version + 1, source)
        with _mongo_errors():
            previous = self._settings.find_one_and_update(
                {"_id": SETTINGS_ID, "version": current.version},
                {"$set": fields},
                return_document=ReturnDocument.BEFORE,
            )
            if previous is None:
                raise SettingsConflictError(CONFLICT_MESSAGE)
            self._keep_history(previous)
        return _to_stored(fields)

    def _keep_history(self, previous: dict[str, Any]) -> None:
        self._history.insert_one({k: v for k, v in previous.items() if k != "_id"})
        stale = self._history.find({}, {"_id": 1}).sort("version", DESCENDING).skip(KEEP_HISTORY)
        stale_ids = [document["_id"] for document in stale]
        if stale_ids:
            self._history.delete_many({"_id": {"$in": stale_ids}})


def open_store() -> JobSettingsStore:
    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB_NAME", "job_scraper")
    timeout = int(os.environ.get("MONGO_SERVER_SELECTION_TIMEOUT_MS", "3000"))
    return JobSettingsStore(MongoClient(uri, serverSelectionTimeoutMS=timeout)[db_name])


def load_app_config(path: Path, store: JobSettingsStore) -> AppConfig:
    machine = read_machine_settings(path)
    return parse({**machine, **store.read().settings}, resolve_proxy_url())
