from __future__ import annotations

import pytest

from scraper.api.client import ApiError
from scraper.api.jobstreet import JobstreetApi
from scraper.types import empty_job
from tests.api_fakes import FakeResponse, make_client


def _item(job_id: str, **overrides):
    item = {
        "id": job_id,
        "title": "Devops",
        "companyName": "Platinumetrix Global Innovations",
        "advertiser": {"id": "61020132", "description": "PT Platinumetrix Global Inovasi"},
        "locations": [{"label": "Jakarta", "countryCode": "ID"}],
        "salaryLabel": "Rp 9.000.000 – Rp 12.000.000 per month",
        "listingDate": "2026-10-26T07:34:52Z",
        "listingDateDisplay": "6h ago",
        "workTypes": ["Contract/Temp"],
        "workArrangements": {"data": [{"id": "1", "label": {"text": "On-site"}}]},
    }
    item.update(overrides)
    return item


def test_search_maps_fields_and_sends_params():
    client, session = make_client(
        [FakeResponse(payload={"data": [_item("95497990")], "totalCount": 1})]
    )
    jobs = JobstreetApi(client).search("devops", "Jakarta Raya", 72, 30)

    params = session.calls[0][2]["params"]
    assert params["siteKey"] == "ID-Main"
    assert params["keywords"] == "devops"
    assert params["where"] == "Jakarta Raya"
    assert params["daterange"] == "3"
    assert params["pageSize"] == "30"
    assert params["page"] == "1"

    job = jobs[0]
    assert job["site"] == "jobstreet"
    assert job["company"] == "PT Platinumetrix Global Inovasi"
    assert job["job_id"] == "95497990"
    assert job["url"] == "https://id.jobstreet.com/id/job/95497990"
    assert job["location"] == "Jakarta"
    assert job["posted_at"] == "2026-10-26T07:34:52+00:00"
    assert job["posted_date"] == "6h ago"
    assert job["employment_type"] == "contract/temp"
    assert job["work_type"] == "on-site"
    assert job["requirements"] is None


def test_country_call_omits_where_and_no_age_omits_daterange():
    client, session = make_client([FakeResponse(payload={"data": []})])
    JobstreetApi(client).search("devops", None, None, 30)
    params = session.calls[0][2]["params"]
    assert "where" not in params
    assert "daterange" not in params


def test_pages_until_limit():
    page1 = {"data": [_item(str(i)) for i in range(100)]}
    page2 = {"data": [_item(str(i)) for i in range(100, 150)]}
    client, session = make_client([FakeResponse(payload=page1), FakeResponse(payload=page2)])
    jobs = JobstreetApi(client).search("devops", "Jakarta Raya", 72, 150)
    assert len(jobs) == 150
    assert [c[2]["params"]["page"] for c in session.calls] == ["1", "2"]


def test_stops_on_short_page():
    client, session = make_client([FakeResponse(payload={"data": [_item("1")]})])
    assert len(JobstreetApi(client).search("devops", "Jakarta Raya", 72, 150)) == 1
    assert len(session.calls) == 1


def test_skips_items_without_title_or_company():
    bad = _item("2", title=None)
    client, _ = make_client([FakeResponse(payload={"data": [bad, _item("1")]})])
    assert [j["job_id"] for j in JobstreetApi(client).search("devops", None, None, 30)] == ["1"]


def test_missing_data_list_is_an_error():
    client, _ = make_client([FakeResponse(payload={"error": "nope"})])
    with pytest.raises(ApiError):
        JobstreetApi(client).search("devops", None, None, 30)


def test_detail_returns_markdown_from_graphql():
    payload = {"data": {"jobDetails": {"job": {"content": "<p>Pengalaman Devops</p>"}}}}
    client, session = make_client([FakeResponse(payload=payload)])
    job = empty_job("jobstreet", "Devops", "PT X")
    job["job_id"] = "95497990"
    assert JobstreetApi(client).detail(job) == "Pengalaman Devops"
    method, url, kwargs = session.calls[0]
    assert (method, url) == ("POST", "https://id.jobstreet.com/graphql")
    assert kwargs["json"]["variables"]["jobId"] == "95497990"
    assert kwargs["headers"]["seek-request-country"] == "ID"


def test_detail_without_job_id_returns_none():
    client, session = make_client([])
    assert JobstreetApi(client).detail(empty_job("jobstreet", "T", "C")) is None
    assert session.calls == []
