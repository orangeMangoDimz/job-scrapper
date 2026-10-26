from __future__ import annotations

import threading

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


def test_no_sleep_when_delay_already_elapsed():
    session = FakeSession([FakeResponse(payload={}), FakeResponse(payload={})])
    sleeps: list[float] = []
    ticks = iter([0.0, 10.0])
    client = ApiClient(
        session_factory=lambda: session,
        sleep=sleeps.append,
        rand=lambda low, high: 1.5,
        clock=lambda: next(ticks),
    )
    client.get_json("https://x.test/1")
    client.get_json("https://x.test/2")
    assert sleeps == []


def test_concurrent_calls_get_distinct_paced_slots():
    # detail calls run in a thread pool sharing one client: each must get its own slot,
    # not all sleep the same delay and then fire together
    responses = [FakeResponse(payload={}) for _ in range(4)]
    session = FakeSession(responses)
    sleeps: list[float] = []
    lock = threading.Lock()
    created: list[int] = []

    def factory():
        created.append(1)
        return session

    def record(seconds: float) -> None:
        with lock:
            sleeps.append(seconds)

    client = ApiClient(
        session_factory=factory, sleep=record, rand=lambda low, high: 1.5, clock=lambda: 0.0
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


def test_error_message_keeps_body_out_of_code():
    client, _ = make_client([FakeResponse(status_code=429, text="<html>blocked</html>")])
    with pytest.raises(ApiError) as err:
        client.get_json("https://x.test/a")
    assert err.value.code == "http_429"
    assert "<html>" not in err.value.code


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
