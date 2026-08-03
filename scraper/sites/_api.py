from __future__ import annotations

from typing import Any, Literal

from ..log import get_logger

_LOG = get_logger()

# Same Chrome impersonation Indeed uses — mimics a real browser's TLS/JA3
# fingerprint, which is often enough to clear WAFs that block plain clients
# (Glints' firewall in particular). Fails soft so callers can fall back to HTML.
_IMPERSONATE: Literal["chrome131"] = "chrome131"
_TIMEOUT_SEC = 30


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: Any | None = None,
    label: str = "api",
) -> Any | None:
    """Issue a browser-impersonated JSON request. Returns parsed JSON, or None on
    any failure (missing dep, network error, non-200, non-JSON) so the caller can
    fall back to HTML scraping."""
    try:
        from curl_cffi import requests as cffi_requests  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 - fail soft by design
        _LOG.error("[%s] curl_cffi missing: %s", label, exc)
        return None

    try:
        if method.upper() == "GET":
            resp = cffi_requests.get(
                url, headers=headers or {}, impersonate=_IMPERSONATE, timeout=_TIMEOUT_SEC
            )
        else:
            resp = cffi_requests.post(
                url,
                headers=headers or {},
                json=json_body,
                impersonate=_IMPERSONATE,
                timeout=_TIMEOUT_SEC,
            )
    except Exception as exc:  # noqa: BLE001 - fail soft by design
        _LOG.warning("[%s] request error: %s: %s", label, type(exc).__name__, exc)
        return None

    if resp.status_code != 200:
        _LOG.warning("[%s] status=%d body=%s", label, resp.status_code, resp.text[:200])
        return None
    try:
        return resp.json()
    except ValueError as exc:  # noqa: BLE001
        _LOG.warning("[%s] non-JSON response: %s", label, exc)
        return None
