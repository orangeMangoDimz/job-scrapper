"""Constants and the environments.yaml manifest loader.

REPO_ROOT mirrors the shell scripts' resolution: the parent of scripts/.
The manifest is parsed into frozen dataclasses; any structural problem raises
ManifestError with a message the launcher prints before exiting.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

# scripts/manage_tui/model.py -> parents[2] == repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
MANIFEST_PATH = SCRIPTS_DIR / "environments.yaml"

MCP_PORT = 8080

# compose service name -> container_name (from docker-compose.yml)
CONTAINER_NAMES = {
    "scraper-mcp": "job-scraper-mcp",
    "mongo": "job-scraper-mongo",
    "bot": "job-scraper-bot",
    "output-init": "job-scraper-init",
}


class ManifestError(Exception):
    """Raised when environments.yaml is missing or structurally invalid."""


@dataclass(frozen=True)
class ProxyCheck:
    check_url: str


@dataclass(frozen=True)
class Environment:
    name: str
    description: str
    compose_files: tuple[str, ...]
    proxy: ProxyCheck | None


@dataclass(frozen=True)
class Manifest:
    default_environment: str
    environments: dict[str, Environment]


def load_manifest(path: Path = MANIFEST_PATH) -> Manifest:
    if not path.exists():
        raise ManifestError(f"Environment manifest not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ManifestError(f"Invalid YAML in {path}: {exc}") from exc

    envs_raw = raw.get("environments")
    if not isinstance(envs_raw, dict) or not envs_raw:
        raise ManifestError(f"{path}: 'environments' must be a non-empty mapping")

    environments = {name: _parse_environment(path, name, body) for name, body in envs_raw.items()}

    default_env = raw.get("default_environment") or next(iter(environments))
    if default_env not in environments:
        raise ManifestError(f"{path}: default_environment '{default_env}' is not defined")
    return Manifest(default_environment=default_env, environments=environments)


def _parse_environment(path: Path, name: str, body: object) -> Environment:
    if not isinstance(body, dict):
        raise ManifestError(f"{path}: environment '{name}' must be a mapping")

    compose_files = body.get("compose_files")
    if not isinstance(compose_files, list) or not compose_files:
        raise ManifestError(f"{path}: environment '{name}' needs a non-empty 'compose_files' list")

    return Environment(
        name=name,
        description=str(body.get("description", "")),
        compose_files=tuple(str(f) for f in compose_files),
        proxy=_parse_proxy(path, name, body.get("proxy")),
    )


def _parse_proxy(path: Path, name: str, raw: object) -> ProxyCheck | None:
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise ManifestError(f"{path}: environment '{name}' proxy must be a mapping")
    try:
        return ProxyCheck(check_url=str(raw["check_url"]))
    except KeyError as exc:
        raise ManifestError(f"{path}: environment '{name}' proxy missing key {exc}") from exc
