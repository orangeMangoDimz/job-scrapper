from __future__ import annotations

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
    )
    client.get_json("https://x.test/1")
    client.get_json("https://x.test/2")
    assert sleeps == [1.5]


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
