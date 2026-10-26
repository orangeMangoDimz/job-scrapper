from __future__ import annotations

import pytest

from scraper.api.client import ApiError
from scraper.api.linkedin import LinkedinApi
from scraper.types import empty_job
from tests.api_fakes import FakeResponse, make_client


def _card(job_id: int, location: str = "Jakarta, Indonesia") -> str:
    return (
        "<li><div class='base-search-card'>"
        f"<a class='base-card__full-link' href='https://id.linkedin.com/jobs/view/devops-{job_id}?trk=x'></a>"
        f"<h3 class='base-search-card__title'>DevOps {job_id}</h3>"
        "<h4 class='base-search-card__subtitle'><a>Acme</a></h4>"
        f"<span class='job-search-card__location'>{location}</span>"
        "<time class='job-search-card__listdate' datetime='2026-10-25'>1 day ago</time>"
        "</div></li>"
    )


def _page(start: int, count: int) -> FakeResponse:
    return FakeResponse(text="".join(_card(i) for i in range(start, start + count)))


def test_sends_location_tpr_and_start():
    client, session = make_client([_page(0, 3)])
    jobs = LinkedinApi(client).search("devops", "Jakarta, Indonesia", 72, 30)
    assert len(session.calls) == 1  # short page = last page, no extra request
    params = session.calls[0][2]["params"]
    assert params == {
        "keywords": "devops",
        "location": "Jakarta, Indonesia",
        "f_TPR": "r259200",
        "start": "0",
    }
    assert len(jobs) == 3
    assert jobs[0]["site"] == "linkedin"
    assert jobs[0]["location"] == "Jakarta, Indonesia"


def test_pages_by_ten_until_limit():
    client, session = make_client([_page(0, 10), _page(10, 10), _page(20, 10)])
    jobs = LinkedinApi(client).search("devops", "Jakarta, Indonesia", None, 25)
    assert len(jobs) == 25
    assert [c[2]["params"]["start"] for c in session.calls] == ["0", "10", "20"]
    assert "f_TPR" not in session.calls[0][2]["params"]


def test_stops_on_empty_page():
    client, session = make_client([_page(0, 10), FakeResponse(text="")])
    assert len(LinkedinApi(client).search("devops", "Indonesia", None, 50)) == 10
    assert len(session.calls) == 2


def test_rate_limit_raises_for_fallback():
    client, _ = make_client([FakeResponse(status_code=429)])
    with pytest.raises(ApiError):
        LinkedinApi(client).search("devops", "Indonesia", None, 10)


def test_detail_is_none_so_runner_uses_job_page():
    client, _ = make_client([])
    assert LinkedinApi(client).detail(empty_job("linkedin", "T", "C")) is None
