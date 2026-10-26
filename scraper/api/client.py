from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any

_IMPERSONATE = "chrome131"
_TIMEOUT_SECONDS = 30
_ERROR_BODY_CHARS = 200
DEFAULT_DELAY_SECONDS: tuple[float, float] = (1.0, 2.0)


class ApiError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class ApiClient:
    """One curl_cffi session per (site, keyword) run, with jittered pacing between calls."""

    def __init__(
        self,
        proxy: str | None = None,
        delay: tuple[float, float] = DEFAULT_DELAY_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        rand: Callable[[float, float], float] = random.uniform,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._proxy = proxy
        self._delay = delay
        self._sleep = sleep
        self._rand = rand
        self._session_factory = session_factory or self._default_session
        self._session: Any = None
        self._has_requested = False

    def _default_session(self) -> Any:
        from curl_cffi import requests as cffi_requests  # type: ignore[attr-defined]

        proxies = {"http": self._proxy, "https": self._proxy} if self._proxy else None
        return cffi_requests.Session(impersonate=_IMPERSONATE, proxies=proxies)

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        if self._session is None:
            self._session = self._session_factory()
        if self._has_requested:
            self._sleep(self._rand(*self._delay))
        self._has_requested = True
        try:
            response = self._session.request(method, url, timeout=_TIMEOUT_SECONDS, **kwargs)
        except Exception as exc:
            raise ApiError("runtime_error", f"{type(exc).__name__}: {exc}") from exc
        if response.status_code != 200:
            raise ApiError(f"http_{response.status_code}", response.text[:_ERROR_BODY_CHARS])
        return response

    def warm(self, url: str) -> None:
        self._request("GET", url)

    def get_text(
        self, url: str, params: dict[str, str] | None = None, headers: dict[str, str] | None = None
    ) -> str:
        return self._request("GET", url, params=params, headers=headers).text

    def get_json(
        self, url: str, params: dict[str, str] | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        return _json_object(self._request("GET", url, params=params, headers=headers))

    def post_json(
        self, url: str, body: dict[str, Any], headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        return _json_object(self._request("POST", url, json=body, headers=headers))


def _json_object(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ApiError("non_json", str(exc)) from exc
    if not isinstance(payload, dict):
        raise ApiError("non_json", "top-level JSON is not an object")
    return payload


def graphql_data(payload: dict[str, Any], field: str) -> Any:
    errors = payload.get("errors")
    if errors:
        raise ApiError("graphql_error", str(errors)[:_ERROR_BODY_CHARS])
    data = (payload.get("data") or {}).get(field)
    if data is None:
        raise ApiError("graphql_error", f"missing data.{field}")
    return data
