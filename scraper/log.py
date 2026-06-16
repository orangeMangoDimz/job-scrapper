# scraper/log.py
"""Central logger — loguru is the engine (Factor XI).

`get_logger()` returns loguru's `logger`, configured ONCE from `scraper.settings`:
a single stdout sink (JSON by default via serialize; `plain` opts out) plus an
opt-in rotating file when LOG_FILE is set. Third-party stdlib logs (uvicorn,
FastMCP, pymongo) are routed into loguru via a root InterceptHandler so the whole
process emits one stream. Idempotent across module reloads (tests reload it).
"""

from __future__ import annotations

import inspect
import logging
import sys
from pathlib import Path

import loguru
from loguru import logger

from . import settings

# Plain, color-free, deterministic (clean in `docker logs`; stable for tests).
_PLAIN_FMT = "{time:YYYY-MM-DD HH:mm:ss.SSS} [{level}] {name}: {message}"

_configured: bool = False


class _InterceptHandler(logging.Handler):
    """Forward stdlib LogRecords into loguru (capture uvicorn/pymongo/FastMCP)."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        # Walk out of the logging module so loguru records the real caller.
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1
        # Pass the already-%-interpolated text as an ARGUMENT, never as the
        # template — third-party messages may contain literal {} that would
        # otherwise crash loguru's str.format-based parser.
        logger.opt(depth=depth, exception=record.exc_info).log(level, "{}", record.getMessage())


def _resolve_level() -> str:
    return settings.LOG_LEVEL if settings.LOG_LEVEL in logging.getLevelNamesMapping() else "INFO"


def get_logger() -> loguru.Logger:
    global _configured
    if _configured:
        return logger

    level = _resolve_level()
    use_json = settings.LOG_FORMAT == "json"

    logger.remove()  # drop loguru's default stderr sink
    logger.add(
        sys.stdout,
        level=level,
        serialize=use_json,
        format=_PLAIN_FMT,
        colorize=False,
        backtrace=False,
        diagnose=False,
        enqueue=False,  # synchronous so pytest capsys sees output immediately
    )
    if settings.LOG_FILE:
        Path(settings.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            settings.LOG_FILE,
            level=level,
            serialize=use_json,
            format=_PLAIN_FMT,
            colorize=False,
            rotation=settings.LOG_FILE_MAX_BYTES,
            retention=settings.LOG_FILE_BACKUP_COUNT,
            encoding="utf-8",
        )

    # Capture-everything: route ALL stdlib logging through loguru.
    logging.basicConfig(handlers=[_InterceptHandler()], level=level, force=True)

    _configured = True
    return logger
