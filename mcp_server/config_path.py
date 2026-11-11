from __future__ import annotations

import os
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(os.environ.get("SCRAPER_CONFIG", "config.yaml"))
