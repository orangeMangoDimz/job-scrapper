from __future__ import annotations

from typing import Any

from scraper.api.client import ApiClient


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_client(responses: list[FakeResponse | Exception]) -> tuple[ApiClient, FakeSession]:
    session = FakeSession(responses)
    client = ApiClient(session_factory=lambda: session, sleep=lambda _s: None)
    return client, session
