from __future__ import annotations

import json
import threading
import time

import pytest

from scraper.api.client import ApiError
from scraper.api.glints import COUNTRY_ID, GlintsApi
from scraper.types import empty_job
from tests.api_fakes import FakeResponse, make_client

JAKARTA = "78d63064-78a1-4577-8516-036a6c5e903e"


def _item(job_id: str, **overrides):
    item = {
        "id": job_id,
        "title": "Sr. DevOps",
        "createdAt": "2026-10-26T09:25:59.250383Z",
        "type": "FULL_TIME",
        "workArrangementOption": "HYBRID",
        "minYearsOfExperience": 3,
        "maxYearsOfExperience": 5,
        "company": {"name": "Insignia"},
        "location": {
            "formattedName": "Kebon Jeruk",
            "parents": [
                {"formattedName": "Indonesia", "level": 1},
                {"formattedName": "DKI Jakarta", "level": 2},
                {"formattedName": "Jakarta Barat", "level": 3},
            ],
        },
        "salaries": [
            {
                "CurrencyCode": "IDR",
                "minAmount": 14000000,
                "maxAmount": 15000000,
                "salaryMode": "MONTH",
            }
        ],
    }
    item.update(overrides)
    return item


def _search(items):
    return FakeResponse(payload={"data": {"searchJobsV3": {"hasMore": False, "jobsInPage": items}}})


def test_warms_once_then_searches_with_location_ids():
    client, session = make_client([FakeResponse(text="<html>"), _search([_item("a")]), _search([])])
    api = GlintsApi(client)
    api.search("devops", JAKARTA, 72, 30)
    api.search("devops", JAKARTA, 72, 30)

    assert session.calls[0][0] == "GET"
    assert [c[0] for c in session.calls[1:]] == ["POST", "POST"]
    data = session.calls[1][2]["json"]["variables"]["data"]
    assert data == {
        "SearchTerm": "devops",
        "CountryCode": "ID",
        "LocationIds": [JAKARTA],
        "page": 1,
        "pageSize": 30,
    }


def test_page_size_caps_at_50():
    client, session = make_client([FakeResponse(text=""), _search([])])
    GlintsApi(client).search("devops", JAKARTA, None, 200)
    assert session.calls[1][2]["json"]["variables"]["data"]["pageSize"] == 50


def test_maps_fields():
    client, _ = make_client([FakeResponse(text=""), _search([_item("ead43098")])])
    job = GlintsApi(client).search("devops", JAKARTA, 72, 30)[0]
    assert job["site"] == "glints"
    assert job["company"] == "Insignia"
    assert job["job_id"] == "ead43098"
    assert job["url"] == "https://glints.com/id/opportunities/jobs/ead43098"
    assert job["location"] == "Kebon Jeruk, Jakarta Barat, DKI Jakarta"
    assert job["posted_at"] == "2026-10-26T09:25:59.250383+00:00"
    assert job["salary"] == "IDR 14,000,000 - 15,000,000 per month"
    assert job["employment_type"] == "full_time"
    assert job["work_type"] == "hybrid"
    assert job["experience_level"] == "3-5 years"


def test_country_level_job_location_is_country_name():
    item = _item("x", location={"formattedName": "Indonesia", "parents": []})
    client, _ = make_client([FakeResponse(text=""), _search([item])])
    assert GlintsApi(client).search("devops", COUNTRY_ID, None, 30)[0]["location"] == "Indonesia"


def test_no_salary_and_min_only_experience():
    item = _item("x", salaries=None, maxYearsOfExperience=None)
    client, _ = make_client([FakeResponse(text=""), _search([item])])
    job = GlintsApi(client).search("devops", JAKARTA, None, 30)[0]
    assert job["salary"] is None
    assert job["experience_level"] == "3+ years"


def test_graphql_error_raises():
    error = FakeResponse(payload={"data": None, "errors": [{"message": "please login"}]})
    client, _ = make_client([FakeResponse(text=""), error])
    with pytest.raises(ApiError):
        GlintsApi(client).search("devops", JAKARTA, None, 30)


def test_detail_converts_draftjs():
    raw = json.dumps({"blocks": [{"text": "AWS", "type": "unordered-list-item"}]})
    detail = FakeResponse(payload={"data": {"getJobById": {"descriptionJsonString": raw}}})
    client, session = make_client([FakeResponse(text=""), detail])
    job = empty_job("glints", "T", "C")
    job["job_id"] = "ead43098"
    assert GlintsApi(client).detail(job) == "- AWS"
    assert session.calls[1][2]["json"]["variables"] == {"id": "ead43098"}


class CountingClient:
    """Fake client whose warm-up is slow, to expose a check-then-set race."""

    def __init__(self) -> None:
        self.warms = 0
        self._lock = threading.Lock()

    def warm(self, url: str) -> None:
        time.sleep(0.02)
        with self._lock:
            self.warms += 1

    def post_json(self, url: str, body: dict, headers: dict | None = None) -> dict:
        raw = json.dumps({"blocks": [{"text": "x", "type": "unstyled"}]})
        return {"data": {"getJobById": {"descriptionJsonString": raw}}}


def test_concurrent_detail_calls_warm_up_once():
    client = CountingClient()
    api = GlintsApi(client)  # type: ignore[arg-type]
    barrier = threading.Barrier(4)

    def call(i: int) -> None:
        job = empty_job("glints", "T", "C")
        job["job_id"] = str(i)
        barrier.wait()
        api.detail(job)

    threads = [threading.Thread(target=call, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert client.warms == 1
