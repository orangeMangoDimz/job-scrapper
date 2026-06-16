from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from .config import FetchTuning, redact_proxy_url
from .config_loader import ALLOWED_URL_HOSTS, AppConfig, keyword_slug
from .fetchers import (
    CloudscraperFetcher,
    CurlCffiFetcher,
    FetchChain,
    PlaywrightFetcher,
)
from .log import get_logger
from .sites import SCRAPERS, Scraper
from .sites._dates import parse_to_iso
from .sites._filter import filter_reason, project_jobs
from .sites._location import refresh_index
from .types import CANONICAL_FIELDS, Job

_LOG = get_logger()


@dataclass(frozen=True)
class SiteRunResult:
    """In-memory result of one (keyword, site) scrape.

    ``filtered`` is the post-filter/limit/projection payload (formerly the
    ``{site}.json`` file); ``raw`` is the pre-filter snapshot of all parsed jobs
    (formerly ``{site}.raw.json``). The dict shapes are unchanged so the Mongo
    document and its downstream consumers stay byte-identical.
    """

    keyword: str
    site: str
    filtered: dict[str, Any]
    raw: dict[str, Any]


def default_fetch_chain(proxy: str | None = None, tuning: FetchTuning | None = None) -> FetchChain:
    return FetchChain(
        [
            CurlCffiFetcher(proxy=proxy, tuning=tuning),
            CloudscraperFetcher(proxy=proxy, tuning=tuning),
            PlaywrightFetcher(proxy=proxy, tuning=tuning),
        ]
    )


def _enrich_jobs(jobs: list[Job], keyword: str) -> None:
    for job in jobs:
        if job.get("matched_keyword") is None:
            job["matched_keyword"] = keyword
        if job.get("posted_at") is None:
            job["posted_at"] = parse_to_iso(job.get("posted_date"))


def _within_max_age(job: Job, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    raw = job.get("posted_at")
    if not isinstance(raw, str):
        return True
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed >= cutoff


def _fetch_requirements(
    jobs: list[Job],
    fields: frozenset[str],
    fetcher: FetchChain,
    scraper: Scraper,
) -> None:
    if "requirements" not in fields or not jobs:
        return

    def _fetch_one(job: Job) -> str | None:
        existing = job.get("requirements")
        if isinstance(existing, str) and existing.strip():
            return existing
        url = job.get("url")
        if not url:
            return None
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return None
        if host not in ALLOWED_URL_HOSTS:
            return None
        result = fetcher.fetch(url)
        return scraper.parse_detail(result.html) if result.html else None

    _LOG.info("[{}] fetching requirements for {} job(s)", scraper.name, len(jobs))
    with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as ex:
        futures = {ex.submit(_fetch_one, job): i for i, job in enumerate(jobs)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                jobs[idx]["requirements"] = fut.result()
            except Exception:
                jobs[idx]["requirements"] = None


def run_one(
    scraper: Scraper,
    fetcher: FetchChain,
    keyword: str,
    fields: frozenset[str],
    max_age_hours: int | None,
    content_filter: dict[str, list[str]],
) -> SiteRunResult:
    label = f"{scraper.name}:{keyword_slug(keyword)}"

    _LOG.info("[{}] fetching {}", label, scraper.url)
    result = fetcher.fetch(scraper.url)
    html = result.html
    if not html and scraper.requires_search_html:
        _LOG.error("[{}] FAILED: no html", label)
        return SiteRunResult(
            keyword=keyword,
            site=scraper.name,
            filtered={
                "error": "fetch failed",
                "url": scraper.url,
                "keyword": keyword,
                "attempts": [a.to_dict() for a in result.attempts],
            },
            raw={"keyword": keyword, "count": 0, "jobs": [], "error": "fetch failed"},
        )

    if html:
        _LOG.info("[{}] fetched search html ({} bytes)", label, len(html))
    else:
        _LOG.info("[{}] no search html (scraper handles fetch internally)", label)

    jobs = scraper.parse(html or "")
    parsed_count = len(jobs)
    _LOG.info("[{}] parsed {} job(s)", label, parsed_count)

    _enrich_jobs(jobs, keyword)

    # snapshot ALL parsed jobs (only the site's query-param filtering applied) BEFORE
    # any Python-level filter/limit/projection. project_jobs builds fresh dicts, so the
    # later in-place requirements enrichment cannot leak back into this raw record.
    raw_jobs = project_jobs(jobs, CANONICAL_FIELDS)
    raw_payload = {
        "keyword": keyword,
        "fields": sorted(CANONICAL_FIELDS),
        "count": len(raw_jobs),
        "jobs": raw_jobs,
    }
    _LOG.info("[{}] captured {} raw job(s)", label, len(raw_jobs))

    cutoff: datetime | None = None
    if max_age_hours is not None:
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
        before = len(jobs)
        recent: list[Job] = []
        for job in jobs:
            if _within_max_age(job, cutoff):
                recent.append(job)
            else:
                _LOG.debug(
                    "[{}] drop stale: {!r} posted_at={} < cutoff={}",
                    label,
                    job.get("title"),
                    job.get("posted_at"),
                    cutoff.isoformat(),
                )
        jobs = recent
        _LOG.info(
            "[{}] max_age={}h cutoff={} kept {}/{} (dropped {} stale)",
            label,
            max_age_hours,
            cutoff.isoformat(),
            len(jobs),
            before,
            before - len(jobs),
        )

    if content_filter:
        before = len(jobs)
        matched: list[Job] = []
        for job in jobs:
            reason = filter_reason(job, content_filter)
            if reason is None:
                matched.append(job)
            else:
                _LOG.debug("[{}] drop filter: {!r} {}", label, job.get("title"), reason)
        jobs = matched
        _LOG.info(
            "[{}] filter={} kept {}/{} (dropped {})",
            label,
            content_filter,
            len(jobs),
            before,
            before - len(jobs),
        )

    if len(jobs) > scraper.limit:
        _LOG.info("[{}] capping {} job(s) to limit={}", label, len(jobs), scraper.limit)
        jobs = jobs[: scraper.limit]

    _fetch_requirements(jobs, fields, fetcher, scraper)

    projected = project_jobs(jobs, fields)
    filtered_payload = {
        "keyword": keyword,
        "fields": sorted(fields),
        "max_age_hours": max_age_hours,
        "filter": content_filter or None,
        "count": len(projected),
        "jobs": projected,
    }
    _LOG.info("[{}] done: {} job(s) after filter/limit", label, len(projected))
    return SiteRunResult(
        keyword=keyword,
        site=scraper.name,
        filtered=filtered_payload,
        raw=raw_payload,
    )


def _select_targets(config: AppConfig, requested: Iterable[str]) -> list[str]:
    requested_list = list(requested)
    if requested_list:
        return requested_list
    return list(config.enabled_site_names())


def _build_pairs(sites: list[str], keywords: list[str]) -> list[tuple[str, str]]:
    return [(keyword, site) for keyword in keywords for site in sites]


def run(
    config: AppConfig,
    targets: Iterable[str] = (),
    keywords: Iterable[str] | None = None,
) -> tuple[int, list[SiteRunResult]]:
    selected = _select_targets(config, targets)
    if not selected:
        _LOG.error("[runner] no sites selected (none enabled in config and no CLI args)")
        return 1, []

    unknown = [name for name in selected if name not in SCRAPERS]
    if unknown:
        _LOG.error(
            "[runner] unknown sites: {}. available: {}",
            ", ".join(unknown),
            ", ".join(SCRAPERS),
        )
        return 1, []

    keyword_list = list(keywords) if keywords else list(config.keywords)
    if not keyword_list:
        _LOG.error("[runner] no keywords to scrape")
        return 1, []

    pairs = _build_pairs(selected, keyword_list)
    proxy_url = config.proxy.url if config.proxy else None
    if proxy_url:
        _LOG.info("[runner] using proxy: {}", redact_proxy_url(proxy_url))
    fetcher = default_fetch_chain(proxy=proxy_url, tuning=config.timeouts)

    # Load the wilayah location index fresh from Mongo once, single-threaded, before
    # workers fan out. Reflects current data each run; threads then read it via
    # get_index() during filtering. Degrades to legacy substring if Mongo is absent.
    refresh_index()

    def _process(pair: tuple[str, str]) -> SiteRunResult | None:
        keyword, name = pair
        site_cfg = config.site(name)
        if site_cfg is None:
            _LOG.warning("[runner] '{}' has no entry in config.yaml; skipping", name)
            return None
        scraper_cls = SCRAPERS[name]
        url = site_cfg.url_for(keyword)
        scraper = scraper_cls(url=url, limit=config.limit_for(name), tuning=config.timeouts)
        return run_one(
            scraper,
            fetcher,
            keyword,
            config.fields_for(name),
            config.max_age_for(name),
            config.filter_for(name),
        )

    workers = max(1, min(config.concurrency, len(pairs)))
    if workers == 1 or len(pairs) == 1:
        serial: list[SiteRunResult] = [r for pair in pairs if (r := _process(pair)) is not None]
        return 0, serial

    _LOG.info(
        "[runner] running {} (keyword,site) pair(s) with concurrency={}",
        len(pairs),
        workers,
    )
    results: list[SiteRunResult] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scraper") as ex:
        futures = {ex.submit(_process, pair): pair for pair in pairs}
        for fut in as_completed(futures):
            keyword, name = futures[fut]
            try:
                site_result = fut.result()
            except Exception as exc:
                _LOG.opt(exception=True).error(
                    "[{}:{}] thread error: {}", name, keyword_slug(keyword), exc
                )
                continue
            if site_result is not None:
                results.append(site_result)
    return 0, results
