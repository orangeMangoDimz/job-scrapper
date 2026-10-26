from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from scraper.api.client import ApiClient, ApiError, graphql_data
from tests.api_fakes import FakeResponse, FakeSession, make_client


def test_get_json_returns_payload_and_passes_params():
    client, session = make_client([FakeResponse(payload={"data": [1]})])
    assert client.get_json("https://x.test/a", params={"q": "devops"}) == {"data": [1]}
    method, url, kwargs = session.calls[0]
    assert (method, url, kwargs["params"]) == ("GET", "https://x.test/a", {"q": "devops"})


def test_post_json_sends_body_and_headers():
    client, session = make_client([FakeResponse(payload={"ok": True})])
    client.post_json("https://x.test/g", {"query": "q"}, headers={"h": "1"})
    _, _, kwargs = session.calls[0]
    assert kwargs["json"] == {"query": "q"}
    assert kwargs["headers"] == {"h": "1"}


def test_non_200_raises_http_code():
    client, _ = make_client([FakeResponse(status_code=429, text="slow down")])
    with pytest.raises(ApiError) as err:
        client.get_json("https://x.test/a")
    assert err.value.code == "http_429"


def test_network_exception_raises_runtime_error():
    client, _ = make_client([ConnectionError("boom")])
    with pytest.raises(ApiError) as err:
        client.get_text("https://x.test/a")
    assert err.value.code == "runtime_error"


def test_non_json_raises():
    client, _ = make_client([FakeResponse(payload=None, text="<html>")])
    with pytest.raises(ApiError) as err:
        client.get_json("https://x.test/a")
    assert err.value.code == "non_json"


def test_non_object_json_raises():
    client, _ = make_client([FakeResponse(payload=[1, 2])])
    with pytest.raises(ApiError) as err:
        client.get_json("https://x.test/a")
    assert err.value.code == "non_json"


def test_pacing_sleeps_between_calls_not_before_first():
    session = FakeSession([FakeResponse(payload={}), FakeResponse(payload={})])
    sleeps: list[float] = []
    client = ApiClient(
        session_factory=lambda: session,
        sleep=sleeps.append,
        rand=lambda low, high: (low + high) / 2,
        clock=lambda: 0.0,
    )
    client.get_json("https://x.test/1")
    client.get_json("https://x.test/2")
    assert sleeps == [1.5]


class FakeClock:
    """Manual clock; `advance` simulates time passing (e.g. a slow response)."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class SlowSession(FakeSession):
    """Each request moves the fake clock forward, like a response that takes time."""

    def __init__(self, responses: list[FakeResponse], clock: FakeClock, seconds: float) -> None:
        super().__init__(responses)
        self._clock = clock
        self._seconds = seconds

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self._clock.advance(self._seconds)
        return super().request(method, url, **kwargs)


def test_no_sleep_when_delay_already_elapsed():
    clock = FakeClock()
    session = FakeSession([FakeResponse(payload={}), FakeResponse(payload={})])
    sleeps: list[float] = []
    client = ApiClient(
        session_factory=lambda: session,
        sleep=sleeps.append,
        rand=lambda low, high: 1.5,
        clock=clock,
    )
    client.get_json("https://x.test/1")
    clock.advance(10.0)
    client.get_json("https://x.test/2")
    assert sleeps == []


def test_partially_elapsed_delay_sleeps_the_rest():
    clock = FakeClock()
    session = FakeSession([FakeResponse(payload={}), FakeResponse(payload={})])
    sleeps: list[float] = []
    client = ApiClient(
        session_factory=lambda: session,
        sleep=sleeps.append,
        rand=lambda low, high: 1.5,
        clock=clock,
    )
    client.get_json("https://x.test/1")
    clock.advance(1.0)
    client.get_json("https://x.test/2")
    assert sleeps == [0.5]


def test_gap_is_measured_from_the_end_of_the_previous_response():
    # LinkedIn needs a real 4-6s idle gap: a slow response must not eat into it
    clock = FakeClock()
    session = SlowSession([FakeResponse(payload={}), FakeResponse(payload={})], clock, 2.0)
    sleeps: list[float] = []
    client = ApiClient(
        session_factory=lambda: session,
        sleep=sleeps.append,
        rand=lambda low, high: 5.0,
        clock=clock,
    )
    client.get_json("https://x.test/1")  # starts at 0, response arrives at 2
    client.get_json("https://x.test/2")  # called at 2: must wait until 2 + 5
    assert sleeps == [5.0]


def test_failed_request_still_paces_the_next_one():
    clock = FakeClock()
    session = FakeSession([FakeResponse(status_code=500), FakeResponse(payload={})])
    sleeps: list[float] = []
    client = ApiClient(
        session_factory=lambda: session,
        sleep=sleeps.append,
        rand=lambda low, high: 1.5,
        clock=clock,
    )
    with pytest.raises(ApiError):
        client.get_json("https://x.test/1")
    client.get_json("https://x.test/2")
    assert sleeps == [1.5]


def test_concurrent_calls_get_distinct_paced_slots():
    # detail calls run in a thread pool sharing one client: each must get its own slot,
    # not all sleep the same delay and then fire together. The slow rand/factory widen
    # the race window so this test fails if the lock is removed.
    session = FakeSession([FakeResponse(payload={}) for _ in range(4)])
    sleeps: list[float] = []
    record_lock = threading.Lock()
    created: list[int] = []

    def slow_factory() -> FakeSession:
        time.sleep(0.02)
        created.append(1)
        return session

    def slow_rand(low: float, high: float) -> float:
        time.sleep(0.01)
        return 1.5

    def record(seconds: float) -> None:
        with record_lock:
            sleeps.append(seconds)

    client = ApiClient(
        session_factory=slow_factory, sleep=record, rand=slow_rand, clock=lambda: 0.0
    )
    barrier = threading.Barrier(4)

    def call(i: int) -> None:
        barrier.wait()
        client.get_json(f"https://x.test/{i}")

    threads = [threading.Thread(target=call, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(sleeps) == [1.5, 3.0, 4.5]
    assert len(created) == 1


def test_warm_does_a_get():
    client, session = make_client([FakeResponse(text="<html>")])
    client.warm("https://x.test/page")
    assert session.calls[0][0:2] == ("GET", "https://x.test/page")


def test_graphql_data_returns_field():
    assert graphql_data({"data": {"search": [1]}}, "search") == [1]


def test_graphql_data_raises_on_errors():
    with pytest.raises(ApiError) as err:
        graphql_data({"data": None, "errors": [{"message": "NO_PERMISSION"}]}, "search")
    assert err.value.code == "graphql_error"


def test_graphql_data_raises_on_missing_field():
    with pytest.raises(ApiError) as err:
        graphql_data({"data": {}}, "search")
    assert err.value.code == "graphql_error"
