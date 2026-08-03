from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from scraper.runner import run_one
from scraper.sites.glints import GlintsScraper
from scraper.sites.jobstreet import JobstreetScraper
from scraper.sites.linkedin import LinkedinScraper
from scraper.types import empty_job


def _make_fetcher(html: str | None):
    fetcher = MagicMock()
    result = MagicMock()
    result.html = html
    result.attempts = ()
    fetcher.fetch.return_value = result
    return fetcher


def _job(title: str, company: str, location: str, posted_at: str | None = None):
    job = empty_job("linkedin", title, company)
    job["location"] = location
    job["url"] = f"https://www.linkedin.com/jobs/view/{title.replace(' ', '')}"
    job["posted_at"] = posted_at
    return job


# Excluded jobs are ordered FIRST so cap-then-filter (the bug) yields count 0
# and filter-then-cap (the fix) yields count 2 — a 0-vs-2 gap proves ordering.
def test_content_filter_runs_before_cap(tmp_path: Path):
    jobs = [
        _job("Bandung Role A", "B1", "Bandung"),
        _job("Bandung Role B", "B2", "Bandung"),
        _job("Jakarta Role A", "J1", "Jakarta"),
        _job("Jakarta Role B", "J2", "Jakarta"),
        _job("Jakarta Role C", "J3", "Jakarta"),
    ]
    scraper = MagicMock()
    scraper.name = "linkedin"
    scraper.url = "https://www.linkedin.com/jobs/search?keywords=x"
    scraper.requires_search_html = True
    scraper.limit = 2
    scraper.collect = MagicMock(return_value=jobs)

    run_one(
        scraper=scraper,
        fetcher=_make_fetcher(html="<html>non-empty</html>"),
        output_dir=tmp_path,
        keyword="data analyst",
        fields=frozenset({"title", "location"}),  # no "requirements" → no detail fetch
        max_age_hours=None,
        content_filter={"location": ["jakarta"]},
    )

    out = json.loads((tmp_path / "linkedin.json").read_text())
    assert out["count"] == 2
    assert all("jakarta" in j["location"].lower() for j in out["jobs"])


def test_max_age_runs_before_cap(tmp_path: Path):
    now = datetime.now(UTC)
    stale = (now - timedelta(hours=100)).isoformat()
    recent = (now - timedelta(hours=1)).isoformat()
    jobs = [
        _job("Stale A", "S1", "Jakarta", posted_at=stale),
        _job("Stale B", "S2", "Jakarta", posted_at=stale),
        _job("Recent A", "R1", "Jakarta", posted_at=recent),
        _job("Recent B", "R2", "Jakarta", posted_at=recent),
        _job("Recent C", "R3", "Jakarta", posted_at=recent),
    ]
    scraper = MagicMock()
    scraper.name = "linkedin"
    scraper.url = "https://www.linkedin.com/jobs/search?keywords=x"
    scraper.requires_search_html = True
    scraper.limit = 2
    scraper.collect = MagicMock(return_value=jobs)

    run_one(
        scraper=scraper,
        fetcher=_make_fetcher(html="<html>non-empty</html>"),
        output_dir=tmp_path,
        keyword="data analyst",
        fields=frozenset({"title", "posted_at"}),
        max_age_hours=24,
        content_filter={},
    )

    out = json.loads((tmp_path / "linkedin.json").read_text())
    assert out["count"] == 2
    assert all(j["title"].startswith("Recent") for j in out["jobs"])


_LINKEDIN_HTML = """<ul>
<li><h3 class="base-search-card__title">Data Analyst</h3>
<h4 class="base-search-card__subtitle"><a>Acme</a></h4>
<span class="job-search-card__location">Jakarta</span>
<a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/123456?x=1">l</a></li>
<li><h3 class="base-search-card__title">Data Engineer</h3>
<h4 class="base-search-card__subtitle"><a>Beta</a></h4>
<span class="job-search-card__location">Bandung</span>
<a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/234567?x=1">l</a></li>
<li><h3 class="base-search-card__title">BI Analyst</h3>
<h4 class="base-search-card__subtitle"><a>Gamma</a></h4>
<span class="job-search-card__location">Jakarta</span>
<a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/345678?x=1">l</a></li>
</ul>"""


def test_linkedin_parse_returns_all_jobs_uncapped():
    scraper = LinkedinScraper(url="https://www.linkedin.com/jobs", limit=2)
    assert len(scraper.parse(_LINKEDIN_HTML)) == 3


_GLINTS_NEXT_DATA = """<!doctype html><html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"jobs":[
{"title":"Data Analyst","companyName":"Acme","slug":"da-1","city":{"name":"Jakarta"}},
{"title":"Data Engineer","companyName":"Beta","slug":"de-2","city":{"name":"Bandung"}},
{"title":"BI Analyst","companyName":"Gamma","slug":"bi-3","city":{"name":"Jakarta"}}
]}}}
</script></body></html>"""


def test_glints_parse_returns_all_jobs_uncapped():
    scraper = GlintsScraper(url="https://glints.com", limit=2)
    assert len(scraper.parse(_GLINTS_NEXT_DATA)) == 3


# Covers the html fallback path (no __NEXT_DATA__) — otherwise dark after the
# XOR re-gate + dropped `skip`. Each job: <a href=.../opportunities/jobs/...>
# with an <h3> title and a sibling .CompanyName under the anchor's parent.
_GLINTS_HTML_FALLBACK = """<html><body>
<div><a href="/id/opportunities/jobs/da-1"><h3>Data Analyst</h3></a><span class="CompanyName">Acme</span></div>
<div><a href="/id/opportunities/jobs/de-2"><h3>Data Engineer</h3></a><span class="CompanyName">Beta</span></div>
<div><a href="/id/opportunities/jobs/bi-3"><h3>BI Analyst</h3></a><span class="CompanyName">Gamma</span></div>
</body></html>"""


def test_glints_parse_html_fallback_uncapped():
    scraper = GlintsScraper(url="https://glints.com", limit=2)
    assert len(scraper.parse(_GLINTS_HTML_FALLBACK)) == 3


_JOBSTREET_NEXT_DATA = """<!doctype html><html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"results":[
{"jobTitle":"Data Analyst","companyName":"Acme","id":"111","locationLabel":"Jakarta"},
{"jobTitle":"Data Engineer","companyName":"Beta","id":"222","locationLabel":"Bandung"},
{"jobTitle":"BI Analyst","companyName":"Gamma","id":"333","locationLabel":"Jakarta"}
]}}}
</script></body></html>"""


def test_jobstreet_parse_returns_all_jobs_uncapped():
    scraper = JobstreetScraper(url="https://id.jobstreet.com", limit=2)
    assert len(scraper.parse(_JOBSTREET_NEXT_DATA)) == 3


# Covers the html fallback path (no __NEXT_DATA__): article[data-card-type=JobCard]
# with [data-automation='jobTitle'] anchor + [data-automation='jobCompany'].
_JOBSTREET_HTML_FALLBACK = """<html><body>
<article data-card-type="JobCard"><a data-automation="jobTitle" href="/job/111">Data Analyst</a><span data-automation="jobCompany">Acme</span></article>
<article data-card-type="JobCard"><a data-automation="jobTitle" href="/job/222">Data Engineer</a><span data-automation="jobCompany">Beta</span></article>
<article data-card-type="JobCard"><a data-automation="jobTitle" href="/job/333">BI Analyst</a><span data-automation="jobCompany">Gamma</span></article>
</body></html>"""


def test_jobstreet_parse_html_fallback_uncapped():
    scraper = JobstreetScraper(url="https://id.jobstreet.com", limit=2)
    assert len(scraper.parse(_JOBSTREET_HTML_FALLBACK)) == 3
