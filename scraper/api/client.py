from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from typing import Any

_IMPERSONATE = "chrome131"
_TIMEOUT_SECONDS = 30
_ERROR_BODY_CHARS = 200
DEFAULT_DELAY_SECONDS: tuple[float, float] = (1.0, 2.0)
# requirements/detail calls run in a thread pool; a short pause keeps them paced but fast
DETAIL_DELAY_SECONDS: tuple[float, float] = (0.3, 0.6)


class ApiError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class ApiClient:
    """One curl_cffi session per (site, keyword) run, with jittered pacing between calls.

    Thread-safe: the detail thread pool shares one client, so each request reserves its own
    start slot under a lock instead of every thread sleeping the same delay and then bursting.
    """

    def __init__(
        self,
        proxy: str | None = None,
        delay: tuple[float, float] = DEFAULT_DELAY_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        rand: Callable[[float, float], float] = random.uniform,
        session_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._proxy = proxy
        self._delay = delay
        self._sleep = sleep
        self._rand = rand
        self._session_factory = session_factory or self._default_session
        self._clock = clock
        self._session: Any = None
        self._lock = threading.Lock()
        # earliest start time for the next request; None until the first request
        self._next_start: float | None = None

    def _default_session(self) -> Any:
        from curl_cffi import requests as cffi_requests  # type: ignore[attr-defined]

        proxies = {"http": self._proxy, "https": self._proxy} if self._proxy else None
        return cffi_requests.Session(impersonate=_IMPERSONATE, proxies=proxies)

    def _reserve_slot(self) -> tuple[float, float]:
        """Create the session once; return (seconds to wait, this request's gap)."""
        with self._lock:
            if self._session is None:
                self._session = self._session_factory()
            now = self._clock()
            start = now if self._next_start is None else max(now, self._next_start)
            gap = self._rand(*self._delay)
            # spaces out concurrent starts (detail thread pool)
            self._next_start = start + gap
            return start - now, gap

    def _release_slot(self, gap: float) -> None:
        """The next request waits `gap` after this response, so a slow response
        does not eat into the idle gap (LinkedIn needs a real 4-6s pause)."""
        with self._lock:
            end_based = self._clock() + gap
            if self._next_start is None or end_based > self._next_start:
                self._next_start = end_based

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        wait, gap = self._reserve_slot()
        if wait > 0:
            self._sleep(wait)
        try:
            response = self._session.request(method, url, timeout=_TIMEOUT_SECONDS, **kwargs)
        except Exception as exc:
            raise ApiError("runtime_error", f"{type(exc).__name__}: {exc}") from exc
        finally:
            self._release_slot(gap)
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
