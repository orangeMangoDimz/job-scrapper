from __future__ import annotations

from scraper.sites.glints import GlintsScraper
from scraper.sites.glints import _job_from_api as glints_job_from_api
from scraper.sites.glints import _keyword_from_url as glints_keyword
from scraper.sites.jobstreet import JobstreetScraper
from scraper.sites.jobstreet import _job_from_api as jobstreet_job_from_api
from scraper.sites.jobstreet import _keyword_from_url as jobstreet_keyword

# --- sample API payloads (shapes taken from the live v5 / searchJobsV3 responses) ---

_JOBSTREET_ITEM = {
    "id": "92996157",
    "title": "Facility Engineer",
    "advertiser": {"id": "60960115", "description": "PT YOFC International Indonesia"},
    "companyName": "YOFC International",
    "locations": [{"label": "Karawang, West Java", "countryCode": "ID"}],
    "listingDate": "2026-06-29T02:53:00Z",
    "salaryLabel": "Rp 10,000,000",
    "workTypes": ["Full time"],
    "workArrangements": {"data": [{"id": "1", "label": {"text": "On-site"}}]},
}

_GLINTS_ITEM = {
    "id": "abc-123",
    "title": "Backend Engineer",
    "company": {"name": "Acme Co", "brandName": "Acme"},
    "city": {"name": "Jakarta"},
    "country": {"code": "ID", "name": "Indonesia"},
    "salaries": [
        {
            "salaryType": "MONTHLY",
            "salaryMode": "MONTHLY",
            "maxAmount": 8000000,
            "minAmount": 5000000,
            "CurrencyCode": "IDR",
        }
    ],
    "createdAt": "2026-07-01T10:00:00Z",
}


def test_jobstreet_job_from_api_maps_fields():
    job = jobstreet_job_from_api(_JOBSTREET_ITEM)
    assert job is not None
    assert job["title"] == "Facility Engineer"
    assert job["company"] == "PT YOFC International Indonesia"  # advertiser.description preferred
    assert job["job_id"] == "92996157"
    assert job["url"] == "https://id.jobstreet.com/id/job/92996157"
    assert job["location"] == "Karawang, West Java"
    assert job["salary"] == "Rp 10,000,000"
    assert job["posted_date"] == "2026-06-29T02:53:00Z"
    assert job["employment_type"] == "full time"
    assert job["work_type"] == "on-site"


def test_glints_job_from_api_maps_fields():
    job = glints_job_from_api(_GLINTS_ITEM)
    assert job is not None
    assert job["title"] == "Backend Engineer"
    assert job["company"] == "Acme Co"
    assert job["job_id"] == "abc-123"
    assert job["url"] == "https://glints.com/id/opportunities/jobs/abc-123"
    assert job["location"] == "Jakarta"  # falls back to city.name when no hierarchical location
    assert job["salary"] == "IDR 5000000-8000000 MONTHLY"
    assert job["posted_date"] == "2026-07-01T10:00:00Z"


def test_glints_job_from_api_resolves_district_to_city():
    # Live API returns the location at District level with the City in `parents`;
    # the mapping must resolve to the City so the location filter matches.
    item = {
        "id": "loc-1",
        "title": "Engineer",
        "company": {"name": "Acme"},
        "location": {
            "name": "Cipondoh",
            "formattedName": "Cipondoh",
            "administrativeLevelName": "District",
            "parents": [
                {"administrativeLevelName": "City", "formattedName": "Tangerang", "name": "Tangerang"},
                {"administrativeLevelName": "Province", "formattedName": "Banten", "name": "Banten"},
            ],
        },
    }
    job = glints_job_from_api(item)
    assert job is not None
    assert job["location"] == "Tangerang"


def test_job_from_api_rejects_incomplete_records():
    assert jobstreet_job_from_api({"title": "No Company"}) is None
    assert glints_job_from_api({"title": "No Id", "company": {"name": "X"}}) is None
    assert glints_job_from_api("not a dict") is None


def test_keyword_extraction():
    url = "https://id.jobstreet.com/id/back-end-engineer-jobs?daterange=1&sortmode=ListedDate"
    assert jobstreet_keyword(url) == "back end engineer"
    gurl = "https://glints.com/id/opportunities/jobs/explore?keyword=ai%20engineer&country=ID"
    assert glints_keyword(gurl) == "ai engineer"


_JOBSTREET_NEXT_DATA = """<!doctype html><html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"results":[
{"jobTitle":"HTML Fallback Role","companyName":"FallbackCo","id":"777","locationLabel":"Jakarta"}
]}}}
</script></body></html>"""


def test_jobstreet_collect_prefers_api(monkeypatch):
    scraper = JobstreetScraper(url="https://id.jobstreet.com/id/x-jobs", limit=3, max_pages=2)
    scraper._fetch_api_jobs = lambda: [jobstreet_job_from_api(_JOBSTREET_ITEM)]  # type: ignore[method-assign]
    jobs = scraper.collect(_JOBSTREET_NEXT_DATA)  # html should be ignored
    assert [j["title"] for j in jobs] == ["Facility Engineer"]


def test_jobstreet_collect_falls_back_to_html(monkeypatch):
    scraper = JobstreetScraper(url="https://id.jobstreet.com/id/x-jobs", limit=3, max_pages=2)
    scraper._fetch_api_jobs = lambda: []  # type: ignore[method-assign]  # API empty/blocked
    jobs = scraper.collect(_JOBSTREET_NEXT_DATA)
    assert [j["title"] for j in jobs] == ["HTML Fallback Role"]


_GLINTS_NEXT_DATA = """<!doctype html><html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"jobs":[
{"title":"Glints HTML Role","companyName":"FallbackCo","slug":"gh-1","city":{"name":"Jakarta"}}
]}}}
</script></body></html>"""


def test_glints_collect_falls_back_to_html(monkeypatch):
    scraper = GlintsScraper(url="https://glints.com/x?keyword=x", limit=3, max_pages=2)
    scraper._fetch_api_jobs = lambda: []  # type: ignore[method-assign]
    jobs = scraper.collect(_GLINTS_NEXT_DATA)
    assert [j["title"] for j in jobs] == ["Glints HTML Role"]
