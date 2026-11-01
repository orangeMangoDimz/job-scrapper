from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scraper.api.client import ApiError
from scraper.api.upwork import COMPANY_NAME, GRAPHQL_URL, HOME_URL, PAGE_SIZE, UpworkApi
from scraper.types import JOB_FIELD_ORDER, empty_job
from tests.api_fakes import FakeResponse, make_client

TOKEN_RESPONSE = FakeResponse(cookies={"visitor_gql_token": "tok"})


def _iso(hours_ago: float = 1) -> str:
    moment = datetime.now(UTC) - timedelta(hours=hours_ago)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _item(job_id: str = "1", hours_ago: float = 1, **job_overrides):
    job = {
        "id": job_id,
        "ciphertext": f"~{job_id}",
        "jobType": "HOURLY",
        "hourlyBudgetMin": 18.0,
        "hourlyBudgetMax": 45.0,
        "contractorTier": "ExpertLevel",
        "publishTime": _iso(hours_ago),
        "fixedPriceAmount": None,
    }
    job.update(job_overrides)
    return {
        "id": job_id,
        "title": "Voice AI Agent Developer",
        "description": "Build voice agents.",
        "ontologySkills": [{"prefLabel": "Python"}, {"prefLabel": "Vapi"}],
        "jobTile": {"job": job},
    }


def _page(items, total=None):
    return FakeResponse(
        payload={
            "data": {
                "search": {
                    "universalSearchNuxt": {
                        "visitorJobSearchV1": {
                            "paging": {"total": total or len(items), "offset": 0, "count": 50},
                            "results": items,
                        }
                    }
                }
            }
        }
    )


def test_search_fetches_the_token_then_sends_it_as_bearer():
    client, session = make_client([TOKEN_RESPONSE, _page([_item()])])

    UpworkApi(client).search("python", "Remote", 72, 30)

    assert session.calls[0][:2] == ("GET", HOME_URL)
    method, url, kwargs = session.calls[1]
    assert (method, url) == ("POST", GRAPHQL_URL)
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    request = kwargs["json"]["variables"]["requestVariables"]
    assert request["userQuery"] == "python"
    assert request["sort"] == "recency"
    assert request["paging"] == {"offset": 0, "count": PAGE_SIZE}


def test_search_maps_an_hourly_job():
    client, _ = make_client([TOKEN_RESPONSE, _page([_item("7")])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["site"] == "upwork"
    assert job["company"] == COMPANY_NAME
    assert job["company_id"] is None
    assert job["job_id"] == "7"
    assert job["url"] == "https://www.upwork.com/jobs/~7"
    assert job["location"] == "Remote"
    assert job["work_type"] == "remote"
    assert job["employment_type"] == "hourly"
    assert job["salary"] == "USD 18 - 45 per hour"
    assert (job["salary_min"], job["salary_max"]) == (18.0, 45.0)
    assert job["experience_level"] == "expert"
    assert job["requirements"] == "Build voice agents.\n\nSkills: Python, Vapi"
    assert job["posted_at"] == job["posted_date"]
    assert str(job["posted_at"]).endswith("+00:00")


def test_search_maps_a_fixed_job():
    item = _item(
        jobType="FIXED",
        hourlyBudgetMin=None,
        hourlyBudgetMax=None,
        fixedPriceAmount={"amount": 500.0},
    )
    client, _ = make_client([TOKEN_RESPONSE, _page([item])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["employment_type"] == "fixed"
    assert job["salary"] == "USD 500 fixed"
    assert (job["salary_min"], job["salary_max"]) == (500.0, 500.0)


def test_search_leaves_salary_empty_without_a_budget():
    item = _item(hourlyBudgetMin=None, hourlyBudgetMax=None)
    client, _ = make_client([TOKEN_RESPONSE, _page([item])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["salary"] is None
    assert (job["salary_min"], job["salary_max"]) == (None, None)


def test_search_fills_both_salary_numbers_from_one_hourly_bound():
    item = _item(hourlyBudgetMin=30.0, hourlyBudgetMax=None)
    client, _ = make_client([TOKEN_RESPONSE, _page([item])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["salary"] == "USD 30 per hour"
    assert (job["salary_min"], job["salary_max"]) == (30.0, 30.0)


def test_search_treats_a_zero_budget_as_no_budget():
    item = _item(jobType="FIXED", fixedPriceAmount={"amount": 0})
    client, _ = make_client([TOKEN_RESPONSE, _page([item])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["salary"] is None
    assert (job["salary_min"], job["salary_max"]) == (None, None)


def test_search_reads_budgets_sent_as_text():
    item = _item(hourlyBudgetMin="18.00", hourlyBudgetMax="45.00")
    client, _ = make_client([TOKEN_RESPONSE, _page([item])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["salary"] == "USD 18 - 45 per hour"
    assert (job["salary_min"], job["salary_max"]) == (18.0, 45.0)


def test_search_treats_an_unreadable_budget_as_no_budget():
    item = _item(hourlyBudgetMin="n/a", hourlyBudgetMax=None)
    client, _ = make_client([TOKEN_RESPONSE, _page([item])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["salary"] is None
    assert (job["salary_min"], job["salary_max"]) == (None, None)


def test_search_writes_large_budgets_in_full():
    item = _item(jobType="FIXED", fixedPriceAmount={"amount": 1000000.0})
    client, _ = make_client([TOKEN_RESPONSE, _page([item])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["salary"] == "USD 1,000,000 fixed"


def test_search_keeps_the_description_alone_without_skills():
    item = _item()
    item["ontologySkills"] = None
    client, _ = make_client([TOKEN_RESPONSE, _page([item])])

    [job] = UpworkApi(client).search("python", "Remote", 72, 30)

    assert job["requirements"] == "Build voice agents."


def test_search_skips_an_item_without_a_title_or_ciphertext():
    no_title = _item("1")
    no_title["title"] = ""
    no_cipher = _item("2", ciphertext=None)
    client, _ = make_client([TOKEN_RESPONSE, _page([no_title, no_cipher, _item("3")])])

    jobs = UpworkApi(client).search("python", "Remote", 72, 30)

    assert [job["job_id"] for job in jobs] == ["3"]


def test_search_pages_until_the_limit_with_one_token():
    first = [_item(str(i)) for i in range(PAGE_SIZE)]
    second = [_item(str(i + PAGE_SIZE)) for i in range(PAGE_SIZE)]
    client, session = make_client([TOKEN_RESPONSE, _page(first), _page(second)])

    jobs = UpworkApi(client).search("python", "Remote", 72, 60)

    assert len(jobs) == 60
    assert len(session.calls) == 3
    second_request = session.calls[2][2]["json"]["variables"]["requestVariables"]
    assert second_request["paging"]["offset"] == PAGE_SIZE


def test_search_stops_after_a_short_page():
    client, session = make_client([TOKEN_RESPONSE, _page([_item()])])

    UpworkApi(client).search("python", "Remote", 72, 60)

    assert len(session.calls) == 2


def test_search_stops_paging_once_jobs_pass_max_age():
    fresh_then_stale = [_item(str(i), hours_ago=i * 2) for i in range(PAGE_SIZE)]
    client, session = make_client([TOKEN_RESPONSE, _page(fresh_then_stale)])

    jobs = UpworkApi(client).search("python", "Remote", 72, 200)

    assert len(session.calls) == 2
    assert len(jobs) == PAGE_SIZE


def test_search_pages_without_max_age_until_the_limit():
    first = [_item(str(i), hours_ago=500) for i in range(PAGE_SIZE)]
    client, session = make_client([TOKEN_RESPONSE, _page(first), _page([_item("x")])])

    jobs = UpworkApi(client).search("python", "Remote", None, 200)

    assert len(session.calls) == 3
    assert len(jobs) == PAGE_SIZE + 1


def test_search_raises_when_the_token_cookie_is_missing():
    client, session = make_client([FakeResponse()])

    with pytest.raises(ApiError) as error:
        UpworkApi(client).search("python", "Remote", 72, 30)

    assert error.value.code == "token_missing"
    assert len(session.calls) == 1


def test_search_raises_on_graphql_errors():
    client, _ = make_client(
        [TOKEN_RESPONSE, FakeResponse(payload={"errors": [{"message": "bad"}]})]
    )

    with pytest.raises(ApiError) as error:
        UpworkApi(client).search("python", "Remote", 72, 30)

    assert error.value.code == "graphql_error"


def test_search_raises_when_the_result_is_missing():
    empty = FakeResponse(payload={"data": {"search": {"universalSearchNuxt": {}}}})
    client, _ = make_client([TOKEN_RESPONSE, empty])

    with pytest.raises(ApiError) as error:
        UpworkApi(client).search("python", "Remote", 72, 30)

    assert error.value.code == "graphql_error"


def test_search_raises_on_a_blocked_token_request():
    client, _ = make_client([FakeResponse(status_code=403, text="blocked")])

    with pytest.raises(ApiError) as error:
        UpworkApi(client).search("python", "Remote", 72, 30)

    assert error.value.code == "http_403"


def test_detail_sends_nothing():
    client, session = make_client([])

    assert UpworkApi(client).detail(empty_job("upwork", "Role", COMPANY_NAME)) is None
    assert session.calls == []


def test_empty_job_has_empty_salary_numbers():
    job = empty_job("upwork", "Role", "Upwork Client")

    assert job["salary_min"] is None
    assert job["salary_max"] is None
    assert list(job) == list(JOB_FIELD_ORDER)
