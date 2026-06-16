from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config_loader import ConfigError, load
from .log import get_logger
from .observability import init_sentry
from .runner import run

DEFAULT_CONFIG = Path("config.yaml")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scraper",
        description="Scrape job listings using sites + settings from config.yaml",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="path to YAML config (default: ./config.yaml)",
    )
    parser.add_argument(
        "-k",
        "--keyword",
        action="append",
        dest="keywords",
        default=None,
        help="override keyword(s) from config; pass --keyword multiple times for several",
    )
    parser.add_argument(
        "sites",
        nargs="*",
        help="optional site names to run; overrides 'enabled' flags in config",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    init_sentry()
    args = _parse_args(list(argv if argv is not None else sys.argv[1:]))
    try:
        config = load(args.config)
    except ConfigError as exc:
        get_logger().error("[config] {}", exc)
        return 2
    exit_code, _ = run(config, targets=args.sites, keywords=args.keywords)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
