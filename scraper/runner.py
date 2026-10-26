from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from .api.client import ApiClient, ApiError
from .api.registry import API_SOURCES
from .api.source import search_all
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


def _fetch_requirements(
    jobs: list[Job],
    fields: frozenset[str],
    fetcher: FetchChain,
    scraper: Scraper,
    detail: Callable[[Job], str | None] | None = None,
) -> None:
    if "requirements" not in fields or not jobs:
        return

    def _from_page(job: Job) -> str | None:
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

    def _fetch_one(job: Job) -> str | None:
        existing = job.get("requirements")
        if isinstance(existing, str) and existing.strip():
            return existing
        if detail is not None:
            try:
                text = detail(job)
            except Exception as exc:  # ApiError or a mapping bug: fall back to the job page
                _LOG.debug("[%s] detail api failed for %s: %s", scraper.name, job.get("url"), exc)
                text = None
            if text:
                return text
        return _from_page(job)

    _LOG.info("[%s] fetching requirements for %d job(s)", scraper.name, len(jobs))
    with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as ex:
        futures = {ex.submit(_fetch_one, job): i for i, job in enumerate(jobs)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                jobs[idx]["requirements"] = fut.result()
            except Exception:
                jobs[idx]["requirements"] = None


def _html_jobs(
    scraper: Scraper,
    fetcher: FetchChain,
    keyword: str,
    label: str,
    paths: tuple[Path, Path, Path],
    fallback_reason: str | None,
) -> list[Job] | None:
    json_path, raw_path, debug_path = paths
    _LOG.info("[%s] fetching %s", label, scraper.url)
    result = fetcher.fetch(scraper.url)
    html = result.html
    if not html and scraper.requires_search_html:
        _LOG.error("[%s] FAILED: no html", label)
        json_path.write_text(
            json.dumps(
                {
                    "error": "fetch failed",
                    "url": scraper.url,
                    "keyword": keyword,
                    "attempts": [a.to_dict() for a in result.attempts],
                    "source": "html",
                    "fallback_reason": fallback_reason,
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
        return None

    if html:
        debug_path.write_text(html)
        _LOG.info("[%s] saved raw html → %s (%d bytes)", label, debug_path.name, len(html))
    else:
        _LOG.info("[%s] no search html (scraper handles fetch internally)", label)
    return scraper.parse(html or "")


def run_one(
    scraper: Scraper,
    fetcher: FetchChain,
    output_dir: Path,
    keyword: str,
    fields: frozenset[str],
    max_age_hours: int | None,
    content_filter: dict[str, list[str]],
    *,
    api_search: Callable[[], list[Job]] | None = None,
    api_detail: Callable[[Job], str | None] | None = None,
) -> None:
    label = f"{scraper.name}:{keyword_slug(keyword)}"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{scraper.name}.json"
    raw_path = output_dir / f"{scraper.name}.raw.json"
    debug_path = output_dir / f"{scraper.name}.debug.html"

    jobs: list[Job] | None = None
    source = "html"
    fallback_reason: str | None = None
    if api_search is not None:
        try:
            jobs = api_search()
            source = "api"
            _LOG.info("[%s] api returned %d job(s)", label, len(jobs))
        except ApiError as exc:
            fallback_reason = str(exc)
            _LOG.warning("[%s] api failed (%s); falling back to html", label, exc)
        except Exception as exc:  # unexpected response shape must not kill the pair
            fallback_reason = f"unexpected_error: {type(exc).__name__}: {exc}"
            _LOG.exception("[%s] api crashed; falling back to html", label)

    if jobs is None:
        jobs = _html_jobs(
            scraper, fetcher, keyword, label, (json_path, raw_path, debug_path), fallback_reason
        )
        if jobs is None:
            return

    parsed_count = len(jobs)
    _LOG.info("[%s] parsed %d job(s) via %s", label, parsed_count, source)

    _enrich_jobs(jobs, keyword)

    # snapshot ALL parsed jobs (only the site's query-param filtering applied) BEFORE
    # any Python-level filter/limit/projection. project_jobs builds fresh dicts, so the
    # later in-place requirements enrichment cannot leak back into this raw record.
    raw_jobs = project_jobs(jobs, CANONICAL_FIELDS)
    raw_path.write_text(
        json.dumps(
            {
                "keyword": keyword,
                "fields": sorted(CANONICAL_FIELDS),
                "count": len(raw_jobs),
                "jobs": raw_jobs,
                "source": source,
                "fallback_reason": fallback_reason,
            },
            indent=2,
        )
    )
    _LOG.info("[%s] wrote %s (%d raw job(s))", label, raw_path.name, len(raw_jobs))

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
                    "[%s] drop stale: %r posted_at=%s < cutoff=%s",
                    label,
                    job.get("title"),
                    job.get("posted_at"),
                    cutoff.isoformat(),
                )
        jobs = recent
        _LOG.info(
            "[%s] max_age=%dh cutoff=%s kept %d/%d (dropped %d stale)",
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
                _LOG.debug("[%s] drop filter: %r %s", label, job.get("title"), reason)
        jobs = matched
        _LOG.info(
            "[%s] filter=%s kept %d/%d (dropped %d)",
            label,
            content_filter,
            len(jobs),
            before,
            before - len(jobs),
        )

    if len(jobs) > scraper.limit:
        _LOG.info("[%s] capping %d job(s) to limit=%d", label, len(jobs), scraper.limit)
        jobs = jobs[: scraper.limit]

    _fetch_requirements(
        jobs, fields, fetcher, scraper, detail=api_detail if source == "api" else None
    )

    projected = project_jobs(jobs, fields)
    json_path.write_text(
        json.dumps(
            {
                "keyword": keyword,
                "fields": sorted(fields),
                "max_age_hours": max_age_hours,
                "filter": content_filter or None,
                "count": len(projected),
                "jobs": projected,
                "source": source,
                "fallback_reason": fallback_reason,
            },
            indent=2,
        )
    )
    _LOG.info("[%s] wrote %s", label, json_path.name)


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

    def _process(pair: tuple[str, str]) -> None:
        keyword, name = pair
        site_cfg = config.site(name)
        if site_cfg is None:
            _LOG.warning("[runner] '%s' has no entry in config.yaml; skipping", name)
            return
        scraper_cls = SCRAPERS[name]
        url = site_cfg.url_for(keyword)
        scraper = scraper_cls(url=url, limit=config.limit_for(name))
        keyword_dir = out / keyword_slug(keyword)
        if not keyword_dir.resolve().is_relative_to(out):
            _LOG.warning("[runner] keyword '%s' slug escapes output_dir; skipping", keyword)
            return
        api_search: Callable[[], list[Job]] | None = None
        api_detail: Callable[[Job], str | None] | None = None
        api_cfg = site_cfg.api
        if api_cfg is not None and api_cfg.enabled and name in API_SOURCES:
            api_source = API_SOURCES[name](ApiClient(proxy=proxy_url))
            locations, country_wide = api_cfg.locations, api_cfg.country_wide
            max_age, limit = config.max_age_for(name), config.limit_for(name)

            def _search_api() -> list[Job]:
                return search_all(api_source, keyword, locations, country_wide, max_age, limit)

            api_search = _search_api
            api_detail = api_source.detail
        run_one(
            scraper,
            fetcher,
            keyword_dir,
            keyword,
            config.fields_for(name),
            config.max_age_for(name),
            config.filter_for(name),
            api_search=api_search,
            api_detail=api_detail,
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
