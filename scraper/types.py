from __future__ import annotations

from typing import TypedDict


class Job(TypedDict):
    site: str
    matched_keyword: str | None
    title: str
    company: str
    company_id: str | None
    url: str | None
    location: str | None
    salary: str | None
    posted_date: str | None
    posted_at: str | None
    work_type: str | None
    employment_type: str | None
    experience_level: str | None
    job_id: str | None
    requirements: str | None


JOB_FIELD_ORDER: tuple[str, ...] = (
    "site",
    "matched_keyword",
    "title",
    "company",
    "company_id",
    "url",
    "location",
    "salary",
    "posted_date",
    "posted_at",
    "work_type",
    "employment_type",
    "experience_level",
    "job_id",
    "requirements",
)

CANONICAL_FIELDS: frozenset[str] = frozenset(JOB_FIELD_ORDER)

MANDATORY_FIELDS: frozenset[str] = frozenset({"site", "matched_keyword", "title", "company", "url"})


def empty_job(site: str, title: str, company: str) -> Job:
    return Job(
        site=site,
        matched_keyword=None,
        title=title,
        company=company,
        company_id=None,
        url=None,
        location=None,
        salary=None,
        posted_date=None,
        posted_at=None,
        work_type=None,
        employment_type=None,
        experience_level=None,
        job_id=None,
        requirements=None,
    )
