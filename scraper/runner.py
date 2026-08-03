from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config_loader import ALLOWED_URL_HOSTS, AppConfig, keyword_slug
from .dedup import dedup_key
from .fetchers import (
    CloudscraperFetcher,
    CurlCffiFetcher,
    FetchChain,
    PlaywrightFetcher,
)
from .log import get_logger
from .seen import SeenStore, seen_record
from .sites import SCRAPERS, Scraper
from .sites._dates import parse_to_iso
from .sites._filter import filter_reason, project_jobs
from .sites._location import refresh_index
from .types import CANONICAL_FIELDS, Job

_LOG = get_logger()


def default_fetch_chain(proxy: str | None = None) -> FetchChain:
    return FetchChain(
        [
            CurlCffiFetcher(proxy=proxy),
            CloudscraperFetcher(proxy=proxy),
            PlaywrightFetcher(proxy=proxy),
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


# Descriptions open with company boilerplate ("About <Company>…"); the
# candidate-facing section the bot actually renders starts well into the text
# (median 642 chars over a 29-job sample). Anchor the kept window there, or a
# small cap keeps only the blurb and drops the qualifications entirely.
_REQUIREMENTS_ANCHOR = re.compile(
    r"(requirements?|qualifications?|what we'?re looking for|we need"
    r"|kualifikasi|persyaratan)",
    re.IGNORECASE,
)


def _truncate_requirements(text: object, max_chars: int | None) -> str | None:
    """Cap a raw description. The bot renders only a few bullets from this, so the
    untruncated text is pure payload weight on every run."""
    if not isinstance(text, str):
        return None
    if max_chars is None or len(text) <= max_chars:
        return text
    match = _REQUIREMENTS_ANCHOR.search(text)
    start = match.start() if match else 0
    window = text[start : start + max_chars].rstrip()
    return f"{'…' if start else ''}{window}{'…' if start + max_chars < len(text) else ''}"


def _fetch_requirements(
    jobs: list[Job],
    fields: frozenset[str],
    fetcher: FetchChain,
    scraper: Scraper,
    max_chars: int | None = None,
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

    _LOG.info("[%s] fetching requirements for %d job(s)", scraper.name, len(jobs))
    with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as ex:
        futures = {ex.submit(_fetch_one, job): i for i, job in enumerate(jobs)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                jobs[idx]["requirements"] = _truncate_requirements(fut.result(), max_chars)
            except Exception:
                jobs[idx]["requirements"] = None


def run_one(
    scraper: Scraper,
    fetcher: FetchChain,
    output_dir: Path,
    keyword: str,
    fields: frozenset[str],
    max_age_hours: int | None,
    content_filter: dict[str, list[str]],
    seen: SeenStore | None = None,
    max_pages: int = 1,
    page_delay_sec: float = 0.0,
    requirements_max_chars: int | None = None,
) -> None:
    # No injected store → in-run-only dedup, no persistence (CLI/unit path).
    if seen is None:
        seen = SeenStore(use_mongo=False)

    label = f"{scraper.name}:{keyword_slug(keyword)}"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{scraper.name}.json"
    raw_path = output_dir / f"{scraper.name}.raw.json"
    debug_path = output_dir / f"{scraper.name}.debug.html"

    cutoff: datetime | None = None
    if max_age_hours is not None:
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)

    pages = max(1, max_pages)
    all_raw: list[Job] = []  # every distinct job parsed across the pages we fetched
    raw_keys: set[str] = set()
    new_jobs: list[Job] = []  # unseen jobs, capped at scraper.limit — what we post
    new_records: list[dict[str, Any]] = []

    # Paginate until we've collected `limit` brand-new jobs, run out of pages, or
    # hit an exhaustion/repeat/stale signal.
    for page in range(pages):
        page_url = scraper.url if page == 0 else scraper.page_url(page)
        if page_url is None:
            break

        _LOG.info("[%s] fetching page %d %s", label, page, page_url)
        result = fetcher.fetch(page_url)
        html = result.html

        if not html and scraper.requires_search_html:
            if page == 0:
                _LOG.error("[%s] FAILED: no html", label)
                json_path.write_text(
                    json.dumps(
                        {
                            "error": "fetch failed",
                            "url": scraper.url,
                            "keyword": keyword,
                            "attempts": [a.to_dict() for a in result.attempts],
                        },
                        indent=2,
                    )
                )
                # keep raw output in lockstep with json_path: reset it so a stale
                # prior-run raw file is never mis-attributed to this failed run
                raw_path.write_text(
                    json.dumps(
                        {"keyword": keyword, "count": 0, "jobs": [], "error": "fetch failed"},
                        indent=2,
                    )
                )
                return
            _LOG.info("[%s] page %d fetch failed; stopping pagination", label, page)
            break

        if html and page == 0:
            debug_path.write_text(html)
            _LOG.info("[%s] saved raw html → %s (%d bytes)", label, debug_path.name, len(html))

        jobs = scraper.collect(html or "")
        _enrich_jobs(jobs, keyword)
        _LOG.info("[%s] page %d parsed %d job(s)", label, page, len(jobs))

        if not jobs:
            break  # exhausted — no more results

        page_keys = [dedup_key(job) for job in jobs]

        # repeat-page guard: a site that ignores the page param re-serves page 0.
        if page > 0 and all(k in raw_keys for k in page_keys):
            _LOG.info("[%s] page %d repeats earlier results; stopping pagination", label, page)
            break

        # accumulate the raw snapshot (deduped by key) across pages
        for key, job in zip(page_keys, jobs, strict=True):
            if key not in raw_keys:
                raw_keys.add(key)
                all_raw.append(job)

        # deeper pages are older (sites are recency-sorted): if every job on this
        # page is past the max-age cutoff, further pages can only be older too.
        if cutoff is not None and all(not _within_max_age(job, cutoff) for job in jobs):
            _LOG.info("[%s] page %d all past max_age cutoff; stopping pagination", label, page)
            break

        # collect unseen jobs (age + content filtered) up to the per-site limit
        for key, job in zip(page_keys, jobs, strict=True):
            if len(new_jobs) >= scraper.limit:
                break
            if cutoff is not None and not _within_max_age(job, cutoff):
                continue
            if content_filter and filter_reason(job, content_filter) is not None:
                continue
            if seen.is_seen(key):
                continue
            seen.remember_in_run(key)
            new_jobs.append(job)
            new_records.append(seen_record(key, job))

        if len(new_jobs) >= scraper.limit:
            break
        if page + 1 < pages and page_delay_sec > 0:
            time.sleep(page_delay_sec)

    # snapshot ALL parsed jobs (only the site's query-param filtering applied) BEFORE
    # Python-level filter/limit/projection. project_jobs builds fresh dicts, so the
    # later in-place requirements enrichment cannot leak back into this raw record.
    raw_jobs = project_jobs(all_raw, CANONICAL_FIELDS)
    raw_path.write_text(
        json.dumps(
            {
                "keyword": keyword,
                "fields": sorted(CANONICAL_FIELDS),
                "count": len(raw_jobs),
                "jobs": raw_jobs,
            },
            indent=2,
        )
    )
    _LOG.info("[%s] wrote %s (%d raw job(s))", label, raw_path.name, len(raw_jobs))

    _fetch_requirements(new_jobs, fields, fetcher, scraper, requirements_max_chars)

    projected = project_jobs(new_jobs, fields)
    json_path.write_text(
        json.dumps(
            {
                "keyword": keyword,
                "fields": sorted(fields),
                "max_age_hours": max_age_hours,
                "filter": content_filter or None,
                "count": len(projected),
                "jobs": projected,
            },
            indent=2,
        )
    )
    _LOG.info("[%s] wrote %s (%d new job(s))", label, json_path.name, len(projected))

    # Persist the newly-posted identifiers so future runs won't repeat them.
    seen.mark_seen(new_records)


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
    output_dir: Path | None = None,
    keywords: Iterable[str] | None = None,
) -> int:
    out = output_dir or config.output_dir
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()

    selected = _select_targets(config, targets)
    if not selected:
        _LOG.error("[runner] no sites selected (none enabled in config and no CLI args)")
        return 1

    unknown = [name for name in selected if name not in SCRAPERS]
    if unknown:
        _LOG.error(
            "[runner] unknown sites: %s. available: %s",
            ", ".join(unknown),
            ", ".join(SCRAPERS),
        )
        return 1

    keyword_list = list(keywords) if keywords else list(config.keywords)
    if not keyword_list:
        _LOG.error("[runner] no keywords to scrape")
        return 1

    pairs = _build_pairs(selected, keyword_list)
    proxy_url = config.proxy.url if config.proxy else None
    if proxy_url:
        _LOG.info("[runner] using proxy: %s", proxy_url)
    fetcher = default_fetch_chain(proxy=proxy_url)

    # Load the wilayah location index fresh from Mongo once, single-threaded, before
    # workers fan out. Reflects current data each run; threads then read it via
    # get_index() during filtering. Degrades to legacy substring if Mongo is absent.
    refresh_index()

    # Shared across all (keyword, site) pairs so the same posting isn't re-emitted
    # under multiple keywords in one run, and isn't reposted across runs.
    seen = SeenStore()

    def _process(pair: tuple[str, str]) -> None:
        keyword, name = pair
        site_cfg = config.site(name)
        if site_cfg is None:
            _LOG.warning("[runner] '%s' has no entry in config.yaml; skipping", name)
            return
        scraper_cls = SCRAPERS[name]
        url = site_cfg.url_for(keyword)
        max_pages = config.max_pages_for(name, api_backed=scraper_cls.api_backed)
        scraper = scraper_cls(url=url, limit=config.limit_for(name), max_pages=max_pages)
        keyword_dir = out / keyword_slug(keyword)
        if not keyword_dir.resolve().is_relative_to(out):
            _LOG.warning("[runner] keyword '%s' slug escapes output_dir; skipping", keyword)
            return
        run_one(
            scraper,
            fetcher,
            keyword_dir,
            keyword,
            config.fields_for(name),
            config.max_age_for(name),
            config.filter_for(name),
            seen=seen,
            max_pages=max_pages,
            page_delay_sec=config.page_delay_sec,
            requirements_max_chars=config.requirements_max_chars,
        )

    workers = max(1, min(config.concurrency, len(pairs)))
    if workers == 1 or len(pairs) == 1:
        for pair in pairs:
            _process(pair)
        return 0

    _LOG.info(
        "[runner] running %d (keyword,site) pair(s) with concurrency=%d",
        len(pairs),
        workers,
    )
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scraper") as ex:
        futures = {ex.submit(_process, pair): pair for pair in pairs}
        for fut in as_completed(futures):
            keyword, name = futures[fut]
            try:
                fut.result()
            except Exception as exc:
                _LOG.error("[%s:%s] thread error: %s", name, keyword_slug(keyword), exc)
    return 0
