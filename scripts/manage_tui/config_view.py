"""Read-only config display: .env (masked) + machine settings.

Job settings live in Mongo and are edited at /config, so this view does not
show them. Site names come from the seed file: they only change there.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .model import REPO_ROOT, Environment

ENV_PATH = REPO_ROOT / ".env"
SEED_PATH = REPO_ROOT / "seeds" / "job_settings.yaml"

PROXY_ENV_KEY = "SCRAPER_PROXY_URL"
MASK_KEYS = {"MONGO_ROOT_PASSWORD", "DISCORD_BOT_TOKEN", PROXY_ENV_KEY}
SHOWN_ENV_KEYS = (
    "MONGO_ROOT_USER",
    "MONGO_ROOT_PASSWORD",
    "MONGO_DB_NAME",
    "MONGO_COLLECTION_NAME",
    "DISCORD_BOT_TOKEN",
    "DISCORD_CHANNEL_ID",
    PROXY_ENV_KEY,
)


@dataclass(frozen=True)
class ConfigSummary:
    source_label: str
    site_names: list[str]
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
    seed = yaml.safe_load(SEED_PATH.read_text()) or {}
    return ConfigSummary(
        source_label=f"{env.name} (job settings in Mongo, edit at /config)",
        site_names=sorted(seed.get("sites") or {}),
        proxy=_proxy_label(env, env_vars),
        mongo_db=env_vars.get("MONGO_DB_NAME", "job_scraper"),
        mongo_collection=env_vars.get("MONGO_COLLECTION_NAME", "scrape_runs"),
    )


def _proxy_label(env: Environment, env_vars: dict[str, str]) -> str:
    if env.proxy is not None:
        return env.proxy.check_url
    value = env_vars.get(PROXY_ENV_KEY)
    if value is None:
        return f"({PROXY_ENV_KEY} not set in .env: scrapes will stop)"
    return "(disabled)" if value == "(empty)" else value


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}{'*' * 6}{value[-2:]}"
