"""The searchJobsV3 API spells these fields differently from the __NEXT_DATA__
payload; the query previously never requested them, so they were always null."""

from __future__ import annotations

from scraper.sites.glints import _GRAPHQL_QUERY, _job_from_api

_ITEM = {
    "id": "abc123",
    "title": "Backend Engineer",
    "company": {"name": "ACME"},
    "location": {"name": "Cipondoh"},
    "createdAt": "2026-07-18T03:52:19Z",
    "workArrangementOption": "HYBRID",
    "type": "FULL_TIME",
    "minYearsOfExperience": 1,
    "maxYearsOfExperience": 3,
}


def _job(**overrides):
    return _job_from_api({**_ITEM, **overrides})


def test_query_requests_the_new_fields():
    for field in ("workArrangementOption", "type", "minYearsOfExperience",
                  "maxYearsOfExperience"):
        assert field in _GRAPHQL_QUERY


def test_work_and_employment_type_are_mapped_and_normalized():
    job = _job()
    assert job["work_type"] == "hybrid"
    assert job["employment_type"] == "full-time"


def test_experience_range_is_rendered():
    assert _job()["experience_level"] == "1-3 years"


def test_open_ended_span_is_treated_as_unspecified():
    # Glints returns 0-50 when a listing does not really state experience
    assert _job(minYearsOfExperience=0, maxYearsOfExperience=50)["experience_level"] is None


def test_equal_bounds_collapse_to_open_range():
    assert _job(minYearsOfExperience=3, maxYearsOfExperience=3)["experience_level"] == "3+ years"


def test_entry_level_range_survives():
    assert _job(minYearsOfExperience=0, maxYearsOfExperience=1)["experience_level"] == "0-1 years"


def test_missing_experience_is_none():
    item = {k: v for k, v in _ITEM.items()
            if k not in ("minYearsOfExperience", "maxYearsOfExperience")}
    assert _job_from_api(item)["experience_level"] is None
