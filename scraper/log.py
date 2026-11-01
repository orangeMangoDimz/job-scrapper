# scraper/log.py
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from urllib.parse import urlparse, urlunparse

_LOGGER_NAME = "job-scraper"
_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# Reset to False on every module (re)load; set to True after first get_logger() call.
_initialized: bool = False


def get_logger() -> logging.Logger:
    global _initialized

    logger = logging.getLogger(_LOGGER_NAME)

    if _initialized:
        return logger

    # Clear any handlers left over from a previous module load (e.g. test reloads).
    logger.handlers.clear()

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    fmt = logging.Formatter(_FMT)

    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    log_dir = Path("logs")
    log_file = log_dir / "scraper.log"
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    _initialized = True
    return logger


def redact_proxy_url(proxy_url: str) -> str:
    """Hide proxy password in logged/returned strings."""
    try:
        p = urlparse(proxy_url)
        if not p.hostname:
            return proxy_url
        host = p.hostname
        port = f":{p.port}" if p.port else ""
        if p.username is not None and p.username != "":
            netloc = f"{p.username}:***@{host}{port}"
        elif p.password is not None:
            netloc = f"***@{host}{port}"
        else:
            netloc = f"{host}{port}"
        return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))
    except Exception:
        return "<unparseable proxy url>"
