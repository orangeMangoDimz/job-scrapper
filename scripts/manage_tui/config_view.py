"""Read-only config display: .env (masked) + config.yaml (+ dev patch).

The displayed config is merged in Python from the SOURCE files, not read from
the generated /tmp/config.dev.yaml. That file may be stale or absent, and
worse, falling back to base config.yaml would mislead: the dev patch sets
`proxy: ~` while base has a proxy enabled. Merging the source patch here shows
the truth. The authoritative merge that the container actually mounts is still
the `yq` step run at start time.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .model import REPO_ROOT, Environment

ENV_PATH = REPO_ROOT / ".env"
CONFIG_PATH = REPO_ROOT / "config.yaml"

MASK_KEYS = {"MONGO_ROOT_PASSWORD", "DISCORD_WEBHOOK_URL"}
SHOWN_ENV_KEYS = (
    "MONGO_ROOT_USER",
    "MONGO_ROOT_PASSWORD",
    "MONGO_DB_NAME",
    "MONGO_COLLECTION_NAME",
    "DISCORD_WEBHOOK_URL",
    "MAX_CHARS",
    "PROXY_URL",
)


@dataclass(frozen=True)
class ConfigSummary:
    source_label: str
    keywords: list[str]
    enabled_sites: list[str]
    proxy: str
    mongo_db: str
    mongo_collection: str


def parse_env(path: Path = ENV_PATH) -> dict[str, str]:
    """Parse a .env file: split on the first '=' only, skip blanks/comments.

    Values are stripped of surrounding quotes. Tokens/passwords may contain
    '.', base64, '#' or '=', so a naive split would corrupt them.
    """
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def masked_env(path: Path = ENV_PATH) -> dict[str, str]:
    """Display-ready subset of .env with secrets masked."""
    env = parse_env(path)
    shown: dict[str, str] = {}
    for key in SHOWN_ENV_KEYS:
        if key not in env:
            continue
        value = env[key]
        if not value:
            shown[key] = "(empty)"
        elif key in MASK_KEYS:
            shown[key] = _mask(value)
        else:
            shown[key] = value
    return shown


def load_config_summary(env: Environment, env_vars: dict[str, str]) -> ConfigSummary:
    base = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    if env.config_merge is not None:
        patch_path = REPO_ROOT / env.config_merge.patch
        patch = (yaml.safe_load(patch_path.read_text()) or {}) if patch_path.exists() else {}
        merged = _deep_merge(base, patch)
        label = f"{env.name} (config.yaml + {env.config_merge.patch})"
    else:
        merged = base
        label = f"{env.name} (config.yaml)"

    proxy_value = merged.get("proxy")
    sites = merged.get("sites") or {}
    enabled_sites = [
        name for name, body in sites.items() if isinstance(body, dict) and body.get("enabled")
    ]

    return ConfigSummary(
        source_label=label,
        keywords=[str(k) for k in (merged.get("keywords") or [])],
        enabled_sites=sorted(enabled_sites),
        proxy=str(proxy_value) if proxy_value else "(disabled)",
        mongo_db=env_vars.get("MONGO_DB_NAME", "job_scraper"),
        mongo_collection=env_vars.get("MONGO_COLLECTION_NAME", "scrape_runs"),
    )


def _deep_merge(base: dict, patch: dict) -> dict:
    """Recursive dict merge; scalars and lists are replaced (matches yq's *)."""
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}{'*' * 6}{value[-2:]}"
