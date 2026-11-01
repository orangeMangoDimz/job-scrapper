from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from .config_loader import ConfigError
from .job_settings import JobSettingsStore, open_store

DEFAULT_SEED_PATH = Path("seeds/job_settings.yaml")
INVALID_SEED_EXIT_CODE = 2


def seed_file(path: Path, store: JobSettingsStore) -> bool:
    return store.seed(yaml.safe_load(path.read_text()) or {})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scraper.seed_settings",
        description="Insert the first job settings document if it is missing",
    )
    parser.add_argument("--file", type=Path, default=DEFAULT_SEED_PATH)
    args = parser.parse_args(argv)
    try:
        is_inserted = seed_file(args.file, open_store())
    except ConfigError as exc:
        print(f"[job-settings] {exc}", file=sys.stderr)
        return INVALID_SEED_EXIT_CODE
    print("[job-settings] inserted" if is_inserted else "[job-settings] already there, unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
