#!/usr/bin/env python3
"""Interactive Docker manager TUI for the scraper stack.

    python scripts/manage.py

Lets you start / stop / status / logs the docker compose stack per profile
(mcp, mongo, bot) across environments (dev, prod), previewing the exact
command before it runs. Read-only over config: it loads .env, the compose
files, and the seed file for display, never writing back.

Requires the TUI deps (not the repo's runtime deps):

    pip install -r scripts/requirements.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent


def _main() -> int:
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))

    try:
        from manage_tui.app import ManagerApp
        from manage_tui.model import ManifestError, load_manifest
    except ModuleNotFoundError as exc:
        if exc.name in {"textual", "yaml"}:
            sys.stderr.write(
                f"Missing dependency: {exc.name}\n"
                "Install the TUI dependencies, then re-run:\n"
                "  pip install -r scripts/requirements.txt\n"
            )
            return 1
        raise

    try:
        manifest = load_manifest()
    except ManifestError as exc:
        sys.stderr.write(f"Config error: {exc}\n")
        return 1

    ManagerApp(manifest).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
