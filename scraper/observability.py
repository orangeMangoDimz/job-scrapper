"""Sentry error monitoring — toggle-gated (Factor III: config in the env).

Activation requires BOTH ``SENTRY_ENABLED`` and a non-empty ``SENTRY_DSN`` (see
``scraper.settings``). Capture rides on loguru via ``LoguruIntegration``;
``_before_send`` drops routine scrape soft-failures so Sentry never firehoses.
Disabled or missing-dep paths degrade silently — the app keeps running.
"""

from __future__ import annotations

import logging

from . import settings
from .log import get_logger

# Routine, EXPECTED scrape soft-failures (anti-bot walls, fetcher fall-through,
# site soft-fails). Already surfaced structurally in the tool's errors[] list —
# they must NOT become Sentry events. Matched as substrings of the formatted
# log message. Add a marker here, never silence by raising event_level.
_ROUTINE_ERROR_MARKERS: tuple[str, ...] = (
    "FAILED: no html",
    "[curl_cffi] error",
    "[cloudscraper] error",
    "[playwright] error",
    "[playwright] asyncio conflict",
    "[indeed-api]",
)


def _message_of(event: dict, hint: dict) -> str:
    """Best-effort formatted log message. Which field holds it depends on the
    integration/SDK version (loguru vs stdlib) — the net is widened across all
    known shapes and is VERIFIED empirically before the filter is relied on.
    Returns "" when nothing is found (caller fails open).
    """
    logentry = event.get("logentry")
    if isinstance(logentry, dict) and isinstance(logentry.get("message"), str):
        return logentry["message"]
    msg = event.get("message")
    if isinstance(msg, str):
        return msg
    record = hint.get("log_record")
    if record is not None:
        try:
            loguru_rec = getattr(record, "record", None)  # loguru adapter
            if isinstance(loguru_rec, dict) and isinstance(loguru_rec.get("message"), str):
                return loguru_rec["message"]
            get_message = getattr(record, "getMessage", None)  # stdlib LogRecord
            if callable(get_message):
                return str(get_message())
        except Exception:
            return ""
    return ""


def _before_send(event: dict, hint: dict) -> dict | None:
    """Drop routine scrape soft-failures; fail OPEN on anything unexpected."""
    message = _message_of(event, hint)
    if message and any(marker in message for marker in _ROUTINE_ERROR_MARKERS):
        return None
    return event


def init_sentry() -> bool:
    """Initialize Sentry when enabled + DSN present. Returns True if active.

    Calls ``get_logger()`` FIRST so loguru is configured before Sentry attaches
    its sink — ``get_logger()``'s first call does ``logger.remove()`` (wipes all
    sinks), which would otherwise drop the Sentry sink (idempotent afterwards).
    """
    log = get_logger()  # configure loguru BEFORE Sentry attaches its sink

    if not settings.SENTRY_ENABLED:
        return False
    if not settings.SENTRY_DSN:
        log.warning("SENTRY_ENABLED is true but SENTRY_DSN is empty; Sentry disabled")
        return False

    # Optional/heavy dep — documented import exception: soft-degrade if absent.
    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.loguru import LoguruIntegration
    except ImportError as exc:
        log.warning("sentry-sdk not installed ({}); Sentry disabled", exc)
        return False

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        release=settings.SENTRY_RELEASE or None,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,  # never attach IP / request headers
        include_local_variables=False,  # never ship stack-frame locals (proxy/mongo creds)
        before_send=_before_send,
        integrations=[
            LoguruIntegration(level=logging.INFO, event_level=logging.ERROR),
            # neutralize the default stdlib integration: _InterceptHandler
            # re-emits stdlib logs through loguru, so LoggingIntegration would
            # double-capture. LoguruIntegration is the sole event source.
            LoggingIntegration(level=None, event_level=None),
        ],
    )
    log.info("sentry initialized environment={}", settings.SENTRY_ENVIRONMENT)
    return True
