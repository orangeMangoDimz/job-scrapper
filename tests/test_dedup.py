from __future__ import annotations

from scraper.dedup import _normalize_url, dedup_key


def _job(**over):
    base = {
        "site": "linkedin",
        "title": "Data Analyst",
        "company": "ACME",
        "url": None,
        "location": "Jakarta",
        "job_id": None,
    }
    base.update(over)
    return base


def test_dedup_key_prefers_job_id():
    assert dedup_key(_job(job_id="998877", url="https://x/whatever")) == "linkedin:998877"


def test_dedup_key_falls_back_to_normalized_url():
    key = dedup_key(_job(job_id=None, url="https://www.LinkedIn.com/jobs/view/12345/?ref=abc"))
    assert key == "url:https://www.linkedin.com/jobs/view/12345"


def test_dedup_key_last_resort_hash_is_stable():
    job = _job(job_id=None, url=None, title="BI Analyst", company="Beta", location="Bandung")
    k1 = dedup_key(job)
    k2 = dedup_key(dict(job))
    assert k1 == k2
    assert k1.startswith("hash:")


def test_dedup_key_distinguishes_sites_for_same_id():
    a = dedup_key(_job(site="indeed", job_id="42"))
    b = dedup_key(_job(site="glints", job_id="42"))
    assert a != b


def test_normalize_url_strips_query_fragment_and_trailing_slash():
    assert _normalize_url("HTTPS://Host.COM/a/b/?q=1#frag") == "https://host.com/a/b"
