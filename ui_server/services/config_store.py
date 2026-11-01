from __future__ import annotations

import io
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import yaml
from ruamel.yaml import YAML

from scraper.config_loader import ConfigError, load
from ui_server.errors import ConfigInvalidError, ConfigReadOnlyError
from ui_server.schema.config import ConfigUpdateRequest
from ui_server.settings import Settings

KEEP_BACKUPS = 20
YAML_LINE_WIDTH = 4096
TOP_LEVEL_FIELDS = {
    "keywords": "keywords",
    "limit": "limit",
    "max_age_hours": "max_age_hours",
    "proxy_url": "proxy",
}


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _flatten_paths(document: dict[str, Any], prefix: str = "") -> tuple[str, ...]:
    paths: list[str] = []
    for key, value in document.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            paths.extend(_flatten_paths(value, f"{path}."))
        else:
            paths.append(path)
    return tuple(paths)


def _changed_paths(changes: ConfigUpdateRequest) -> tuple[str, ...]:
    top_level = [
        path for field, path in TOP_LEVEL_FIELDS.items() if field in changes.model_fields_set
    ]
    per_site = [
        f"sites.{name}.{field}"
        for name, site in changes.sites.items()
        for field in sorted(site.model_fields_set)
    ]
    return (*top_level, *per_site)


def _new_yaml() -> YAML:
    round_trip = YAML()
    round_trip.preserve_quotes = True
    round_trip.width = YAML_LINE_WIDTH
    round_trip.indent(mapping=2, sequence=4, offset=2)
    return round_trip


def _dump(document: Any) -> str:
    buffer = io.StringIO()
    _new_yaml().dump(document, buffer)
    return buffer.getvalue()


def _apply(document: Any, changes: ConfigUpdateRequest) -> None:
    for field, path in TOP_LEVEL_FIELDS.items():
        if field in changes.model_fields_set:
            document[path] = getattr(changes, field)
    sites = document.get("sites") or {}
    for name, site in changes.sites.items():
        if name not in sites:
            raise ConfigInvalidError(f"Unknown site: {name}")
        for field in site.model_fields_set:
            sites[name][field] = getattr(site, field)


def _validate(text: str) -> None:
    with tempfile.TemporaryDirectory() as folder:
        candidate = Path(folder) / "config.yaml"
        candidate.write_text(text, encoding="utf-8")
        try:
            load(candidate)
        except ConfigError as exc:
            raise ConfigInvalidError(str(exc)) from exc


class ConfigStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()

    def locked_paths(self) -> tuple[str, ...]:
        if self._settings.config_read_only:
            return ()
        return _flatten_paths(self._read_patch())

    def update(self, changes: ConfigUpdateRequest) -> None:
        if self._settings.config_read_only:
            raise ConfigReadOnlyError()
        with self._lock:
            self._reject_locked(changes)
            path = self._settings.config_path
            original = path.read_text(encoding="utf-8")
            document = _new_yaml().load(original)
            _apply(document, changes)
            text = _dump(document)
            merged_text = self._merge_with_patch(text)
            _validate(text)
            _validate(merged_text)
            self._backup(original)
            path.write_text(text, encoding="utf-8")
            self._settings.dev_merged_path.write_text(merged_text, encoding="utf-8")

    def _reject_locked(self, changes: ConfigUpdateRequest) -> None:
        locked = set(self.locked_paths())
        blocked = [path for path in _changed_paths(changes) if path in locked]
        if blocked:
            names = ", ".join(blocked)
            raise ConfigInvalidError(f"Set by config.dev.patch.yaml: {names}")

    def _read_patch(self) -> dict[str, Any]:
        path = self._settings.dev_patch_path
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def _backup(self, original: str) -> None:
        folder = self._settings.backup_dir
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"config.yaml.{time.time_ns()}").write_text(original, encoding="utf-8")
        for stale in sorted(folder.iterdir())[:-KEEP_BACKUPS]:
            stale.unlink()

    def _merge_with_patch(self, text: str) -> str:
        merged = deep_merge(yaml.safe_load(text), self._read_patch())
        return yaml.safe_dump(merged, sort_keys=False)
