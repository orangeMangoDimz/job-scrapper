from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from mcp.server.fastmcp import FastMCP  # type: ignore[import-untyped]
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp_server import mongo
from scraper import settings
from scraper.config import ACCEPT_LANGUAGE, CHROME_IMPERSONATE, USER_AGENT, redact_proxy_url
from scraper.config_loader import AppConfig, ConfigError, load
from scraper.log import get_logger as _get_logger
from scraper.observability import init_sentry
from scraper.runner import run as run_scraper
from scraper.types import JOB_FIELD_ORDER

DEFAULT_CONFIG_PATH = Path(os.environ.get("SCRAPER_CONFIG", "config.yaml"))
DEFAULT_PROXY_TEST_URL = os.environ.get(
    "PROXY_TEST_URL",
    "https://api.ipify.org?format=json",
)
PROXY_TEST_TIMEOUT_SEC = float(os.environ.get("PROXY_TEST_TIMEOUT_SEC", "25"))
HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "8080"))

_STATUS_PATH = Path(settings.STATUS_FILE)
_LOG_PATH: Path | None = Path(settings.LOG_FILE) if settings.LOG_FILE else None

mcp = FastMCP("job-scraper", host=HOST, port=PORT)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> Response:
    # Readiness probe: report Mongo reachability. pymongo is blocking, so run
    # the ping off the event loop. Keep the error out of the body (8080 is
    # host-exposed) and log it server-side instead.
    try:
        await run_in_threadpool(mongo.ping)
    except Exception as exc:  # unreachable / selection timeout / op failure
        log = _get_logger()
        log.warning("health check: mongo ping failed: {}", exc)
        return JSONResponse({"status": "degraded", "mongo": "error"}, status_code=503)
    return JSONResponse({"status": "ok", "mongo": "ok"})


def _load_config(path: Path) -> AppConfig:
    return load(path)


def _build_per_site_counts(results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for group in results:
        keyword = group["keyword"]
        for site_entry in group.get("sites", []):
            counts.setdefault(site_entry["site"], {})[keyword] = site_entry.get("count", 0)
    return counts


def _build_note(errors: list[dict[str, Any]]) -> str | None:
    """Human-readable failure summary, or None when the run had no errors.

    Covers scrape failures and proxy failures alike — a dead proxy surfaces as
    per-(keyword,site) fetch errors, which land in ``errors``.
    """
    if not errors:
        return None
    reasons = "; ".join(f"{e.get('site', '?')}: {e.get('reason', 'unknown')}" for e in errors)
    return f"scrape failed — {reasons}"


def _deep_merge(base: dict, patch: dict) -> dict:
    result = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _atomic_write_yaml(path: Path, data: dict) -> None:
    serialized = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(serialized)
    tmp_path.replace(path)


def _probe_proxy_http(proxy_url: str, test_url: str) -> dict[str, Any]:
    """GET test_url through proxy_url using curl_cffi (same stack as scraper fetchers)."""
    try:
        from curl_cffi import requests as cffi_requests  # type: ignore[attr-defined]
    except Exception as exc:
        return {
            "ok": False,
            "error": f"curl_cffi not available: {type(exc).__name__}: {exc}",
        }

    proxies = {"http": proxy_url, "https": proxy_url}
    try:
        response = cffi_requests.get(
            test_url,
            impersonate=CHROME_IMPERSONATE,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": ACCEPT_LANGUAGE,
            },
            timeout=PROXY_TEST_TIMEOUT_SEC,
            proxies=proxies,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    status = response.status_code
    body = (response.text or "")[:512]
    out: dict[str, Any] = {
        "ok": status == 200,
        "http_status": status,
        "test_url": test_url,
    }
    if status != 200:
        out["error"] = f"HTTP {status}"
        out["response_excerpt"] = body
        return out

    egress_ip: str | None = None
    ct = (response.headers.get("content-type") or "").lower()
    if "json" in ct or body.strip().startswith("{"):
        try:
            data = json.loads(response.text)
            if isinstance(data, dict):
                if isinstance(data.get("ip"), str):
                    egress_ip = data["ip"]
                elif isinstance(data.get("origin"), str):
                    egress_ip = data["origin"].split(",")[0].strip()
        except json.JSONDecodeError:
            pass
    if egress_ip is None and body and len(body) < 64:
        egress_ip = body.strip()

    if egress_ip:
        out["egress_ip"] = egress_ip
    out["response_excerpt"] = body
    return out


def _write_status(result: dict[str, Any], duration: float) -> None:
    now = datetime.now(UTC).isoformat()
    errors: list[dict[str, Any]] = result.get("errors", [])

    last_error: dict[str, Any] | None = None
    if errors:
        last_error = {**errors[-1], "timestamp": now}

    per_site: dict[str, Any] = {}
    for kw_result in result.get("results", []):
        for site_entry in kw_result.get("sites", []):
            name = site_entry.get("site")
            if name:
                per_site[name] = {
                    "last_run_at": now,
                    "last_status": "ok",
                    "last_job_count": site_entry.get("count", 0),
                    "last_error": None,
                }
    for err in errors:
        name = err.get("site")
        if name:
            per_site[name] = {
                "last_run_at": now,
                "last_status": "error",
                "last_job_count": 0,
                "last_error": err.get("reason"),
            }

    existing_per_site: dict[str, Any] = {}
    if _STATUS_PATH.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            existing_per_site = json.loads(_STATUS_PATH.read_text()).get("per_site", {})
    merged_per_site = {**existing_per_site, **per_site}

    total_jobs = sum(
        site_entry.get("count", 0)
        for kw_result in result.get("results", [])
        for site_entry in kw_result.get("sites", [])
    )

    status = {
        "last_run": {
            "timestamp": now,
            "ok": result.get("ok", False),
            "duration_seconds": round(duration, 2),
            "keywords": result.get("keywords", []),
            "sites": result.get("requested_sites", []),
            "total_jobs": total_jobs,
            "error_count": len(errors),
            "errors": errors,
        },
        "last_error": last_error,
        "per_site": merged_per_site,
    }

    _STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATUS_PATH.write_text(json.dumps(status, indent=2))


def _normalize_job_payload(raw_job: Any, site_name: str, keyword: str) -> dict[str, Any]:
    source = raw_job if isinstance(raw_job, dict) else {}
    normalized = {field: source.get(field) for field in JOB_FIELD_ORDER}
    normalized["site"] = source.get("site") or site_name
    normalized["matched_keyword"] = source.get("matched_keyword") or keyword
    return normalized


def _normalize_site_payload(
    payload: dict[str, Any], site_name: str, keyword: str
) -> dict[str, Any]:
    raw_jobs = payload.get("jobs")
    jobs = raw_jobs if isinstance(raw_jobs, list) else []
    normalized_jobs = [
        _normalize_job_payload(job, site_name=site_name, keyword=keyword) for job in jobs
    ]

    raw_fields = payload.get("fields")
    fields = (
        [field for field in raw_fields if isinstance(field, str) and field in JOB_FIELD_ORDER]
        if isinstance(raw_fields, list)
        else []
    )
    if not fields:
        fields = list(JOB_FIELD_ORDER)

    max_age_hours = payload.get("max_age_hours")
    normalized_max_age = max_age_hours if isinstance(max_age_hours, int) else None
    content_filter = payload.get("filter")
    normalized_filter = content_filter if isinstance(content_filter, dict) else None

    return {
        "site": site_name,
        "keyword": keyword,
        "fields": fields,
        "max_age_hours": normalized_max_age,
        "filter": normalized_filter,
        "count": len(normalized_jobs),
        "jobs": normalized_jobs,
    }


@mcp.tool()
def list_sites() -> dict[str, Any]:
    """List sites declared in config.yaml with their enabled status.

    Each site shows its raw url_template plus a sample resolved URL formatted
    against the first configured keyword. The full keyword list is also returned.
    """
    try:
        config = _load_config(DEFAULT_CONFIG_PATH)
    except ConfigError as exc:
        return {"error": str(exc)}
    sample_keyword = config.keywords[0] if config.keywords else ""
    return {
        "keywords": list(config.keywords),
        "limit": config.limit,
        "sites": [
            {
                "name": site.name,
                "enabled": site.enabled,
                "url_template": site.url_template,
                "sample_url": (site.url_for(sample_keyword) if sample_keyword else None),
            }
            for site in config.sites
        ],
    }


@mcp.tool()
def get_config() -> dict[str, Any]:
    """Return the current config.yaml contents as a parsed dict.

    Use this before update_config to inspect the current shape, then send a
    minimal patch to change only what you want.
    """
    if not DEFAULT_CONFIG_PATH.exists():
        return {"error": f"config file not found: {DEFAULT_CONFIG_PATH}"}
    try:
        raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    except yaml.YAMLError as exc:
        return {"error": f"invalid YAML: {exc}"}
    return raw if isinstance(raw, dict) else {}


@mcp.tool()
def get_scrape_response_structure() -> dict[str, Any]:
    """Return canonical schema and example payload for scrape_jobs response."""
    sample_job: dict[str, Any] = {field: None for field in JOB_FIELD_ORDER}
    sample_job["site"] = "jobstreet"
    sample_job["matched_keyword"] = "data analyst"
    sample_job["title"] = "Data Analyst"
    sample_job["company"] = "ACME"
    sample_job["url"] = "https://id.jobstreet.com/job/123"

    return {
        "tool": "scrape_jobs",
        "version": "1.0.0",
        "job_fields": list(JOB_FIELD_ORDER),
        "top_level_fields": [
            "ok",
            "keywords",
            "requested_sites",
            "exit_code",
            "results",
            "errors",
            "mongo_id",
        ],
        "site_result_fields": [
            "site",
            "keyword",
            "fields",
            "max_age_hours",
            "filter",
            "count",
            "jobs",
        ],
        "error_fields": ["keyword", "site", "reason", "attempts"],
        "sample": {
            "ok": True,
            "keywords": ["data analyst"],
            "requested_sites": ["jobstreet"],
            "exit_code": 0,
            "results": [
                {
                    "keyword": "data analyst",
                    "sites": [
                        {
                            "site": "jobstreet",
                            "keyword": "data analyst",
                            "fields": list(JOB_FIELD_ORDER),
                            "max_age_hours": 24,
                            "filter": {"location": ["jakarta"]},
                            "count": 1,
                            "jobs": [sample_job],
                        }
                    ],
                }
            ],
            "errors": [],
        },
    }


@mcp.tool()
def update_config(patch: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge a patch into config.yaml after validating the result.

    The patch is merged into the existing config (nested dicts are merged
    recursively; lists and scalars are replaced). The merged document is
    validated using the same loader the scraper itself uses; on validation
    failure, the file is left untouched and the error is returned.

    A timestamped backup (config.yaml.bak.<unix-ts>) is created before the
    new file is written atomically.

    Args:
        patch: dict to merge in. Examples:
            {"keywords": ["data analyst"]}
            {"max_age_hours": 24}
            {"sites": {"linkedin": {"enabled": false}}}
            {"sites": {"glints": {"max_age_hours": 12}}}

    Returns:
        On success: {ok: True, applied: <merged>, backup: <path>}
        On failure: {ok: False, error: <reason>}
    """
    if not isinstance(patch, dict):
        return {"ok": False, "error": "patch must be a dict"}  # pyright: ignore[reportUnreachable]
    if not DEFAULT_CONFIG_PATH.exists():
        return {"ok": False, "error": f"config file not found: {DEFAULT_CONFIG_PATH}"}

    try:
        current = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text()) or {}
    except yaml.YAMLError as exc:
        return {"ok": False, "error": f"invalid YAML in current config: {exc}"}
    if not isinstance(current, dict):
        return {"ok": False, "error": "current config root must be a mapping"}

    merged = _deep_merge(current, patch)

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as fh:
        yaml.safe_dump(merged, fh, sort_keys=False, allow_unicode=True)
        validation_tmp = Path(fh.name)
    try:
        load(validation_tmp)
    except ConfigError as exc:
        validation_tmp.unlink(missing_ok=True)
        return {"ok": False, "error": f"validation failed: {exc}"}
    finally:
        validation_tmp.unlink(missing_ok=True)

    backup_path = DEFAULT_CONFIG_PATH.with_name(
        f"{DEFAULT_CONFIG_PATH.name}.bak.{int(time.time())}"
    )
    try:
        shutil.copy2(DEFAULT_CONFIG_PATH, backup_path)
    except OSError as exc:
        return {"ok": False, "error": f"backup failed: {exc}"}

    try:
        _atomic_write_yaml(DEFAULT_CONFIG_PATH, merged)
    except OSError as exc:
        return {"ok": False, "error": f"write failed: {exc}"}

    return {"ok": True, "applied": merged, "backup": str(backup_path)}


@mcp.tool()
def get_scrape_status() -> dict[str, Any]:
    """Return the status of the last scrape_jobs run plus recent log lines.

    Returns:
        dict with keys:
            available: false when no run has been recorded yet
            last_run: {timestamp, ok, duration_seconds, keywords, sites,
                       total_jobs, error_count, errors}
            last_error: last error entry with timestamp, or null if last run clean
            per_site: {site_name: {last_run_at, last_status, last_job_count, last_error}}
            recent_logs: last 30 lines from logs/scraper.log (empty list if no log file)
    """
    if not _STATUS_PATH.exists():
        return {"available": False, "message": "No scrape run has been recorded yet."}

    try:
        status = json.loads(_STATUS_PATH.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return {"available": False, "error": f"Could not read status file: {exc}"}

    recent_logs: list[str] = []
    if _LOG_PATH is not None and _LOG_PATH.exists():
        try:
            lines = _LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
            recent_logs = lines[-30:]
        except OSError:
            pass

    return {"available": True, **status, "recent_logs": recent_logs}


@mcp.tool()
def insert_scrape_run(run_data: dict[str, Any]) -> dict[str, Any]:
    """Insert a scraping run record into MongoDB for history tracking.

    Args:
        run_data: Arbitrary dict with run details. Recommended keys:
            run_metadata: {ok, exit_code, keywords, requested_sites, errors,
                           per_site_counts, bot_post_status}
            filtered_results: per-site filtered/projected jobs
            raw_results: per-site unfiltered jobs (only the site's query params)
            note: failure summary string, or null
            channel_id: Discord channel id (never the bot token)
            discord_sent_status: "success" | "failed"

    Returns:
        On success: {ok: true, inserted_id: <str>}
        On failure: {ok: false, error: <str>}
    """
    try:
        inserted_id = mongo.insert_run(run_data)
        return {"ok": True, "inserted_id": inserted_id}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_latest_scrape_run() -> dict[str, Any]:
    """Return the most recent scraping run record from MongoDB.

    Returns:
        {available: false, message: str} when no runs have been recorded
        {available: false, error: str} when MongoDB is unreachable
        {available: true, _id, _created_at, run_metadata, filtered_results,
         raw_results, note, channel_id, discord_sent_status, ...} on success
    """
    try:
        doc = mongo.get_latest_run()
        if doc is None:
            return {"available": False, "message": "No scrape runs recorded yet."}
        return {"available": True, **doc}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


@mcp.tool()
def update_scrape_run(run_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Patch an existing scrape run document (from scrape_jobs' mongo_id).

    Used by the bot to add Discord columns to the SAME run document instead of
    inserting a second one. Recommended patch keys:
        channel_id: str (Discord channel id — NOT the bot token)
        discord_sent_status: "success" | "failed"
        run_metadata.bot_post_status: {total_posted, failed}  (dot-notation key)

    Returns {ok: true, matched: <bool>} or {ok: false, error: <str>}.
    """
    try:
        matched = mongo.update_run(run_id, patch)
        return {"ok": True, "matched": matched}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def test_proxy_connection(
    proxy_url: str | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    """Check that an HTTP(S) request succeeds through the configured proxy.

    Uses the same curl_cffi transport as the scraper fetchers (HTTP, HTTPS,
    SOCKS5 URLs as supported by curl_cffi).

    Args:
        proxy_url: optional override; when omitted, uses ``proxy`` from
            config.yaml. When config has no proxy and this is omitted, returns
            an error.
        url: optional URL to fetch (default: ``PROXY_TEST_URL`` env or
            https://api.ipify.org?format=json). Must be http or https.

    Returns:
        On success: {ok: true, proxy_redacted, test_url, http_status, duration_ms,
            egress_ip? , response_excerpt?}
        On failure: {ok: false, proxy_redacted?, test_url?, error, ...}
    """
    log = _get_logger()
    test_target = (url or "").strip() or DEFAULT_PROXY_TEST_URL

    parsed_test = urlparse(test_target)
    if parsed_test.scheme not in ("http", "https"):
        return {
            "ok": False,
            "error": f"url must be http(s), got scheme={parsed_test.scheme!r}",
        }

    resolved_proxy = (proxy_url or "").strip()
    used_config_proxy = False
    if not resolved_proxy:
        try:
            config = _load_config(DEFAULT_CONFIG_PATH)
        except ConfigError as exc:
            log.warning("test_proxy_connection config error: {}", exc)
            return {"ok": False, "error": str(exc)}
        if not config.proxy:
            return {
                "ok": False,
                "error": (
                    "no proxy in config.yaml and proxy_url not passed — set proxy or pass proxy_url"
                ),
            }
        resolved_proxy = config.proxy.url
        used_config_proxy = True

    redacted = redact_proxy_url(resolved_proxy)
    log.info(
        "test_proxy_connection proxy={} test_url={}",
        redacted,
        test_target,
    )

    t0 = time.monotonic()
    probe = _probe_proxy_http(resolved_proxy, test_target)
    duration_ms = round((time.monotonic() - t0) * 1000, 2)

    base: dict[str, Any] = {
        "proxy_redacted": redacted,
        "test_url": test_target,
        "duration_ms": duration_ms,
    }
    if used_config_proxy:
        base["source"] = "config"

    merged = {**base, **probe}
    if merged.get("ok"):
        log.info(
            "test_proxy_connection ok duration_ms={} egress_ip={}",
            duration_ms,
            merged.get("egress_ip"),
        )
    else:
        log.warning("test_proxy_connection failed: {}", merged.get("error"))
    return merged


@mcp.tool()
def scrape_jobs(
    sites: list[str] | None = None,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """Run the job scraper and return aggregated results.

    Args:
        sites: optional list of site names to scrape. When omitted, runs every
            site marked enabled in config.yaml.
        keywords: optional list of keywords to scrape. When omitted, runs every
            keyword in config.yaml. Useful to ad-hoc query a single term without
            editing config.yaml.

    Returns:
        dict with keys:
            ok: true when every requested site was reached, regardless of job
                count. Zero jobs with ok=true means the site responded but
                nothing matched your filters or date range — this is normal,
                not an error. ok=false means at least one site failed to fetch.
            keywords: list of keywords actually attempted
            requested_sites: list of site names attempted (per keyword)
            exit_code: scraper exit code (0 = ran without fatal error;
                does NOT reflect per-site fetch success — use ok for that)
            results: list grouped by keyword, each entry:
                {keyword, sites: [{site, fields, count, jobs, ...}]}.
                A site entry is absent from this list when its fetch failed
                (see errors). Each job is projected to the fields configured
                for that site and normalized to canonical schema. Canonical
                fields: site, matched_keyword, title, company, url, location,
                salary, posted_date, posted_at, work_type, employment_type,
                experience_level, job_id, requirements. Fields a site cannot
                extract are returned as null.
            errors: list of {keyword, site, reason, attempts?} for any pair
                that failed. Presence of entries here means ok=false.
                `attempts` (when present) lists per-fetcher outcomes:
                [{fetcher, code, detail}]. Codes:
                  - http_<status>     site rejected request (e.g. http_403)
                  - challenge         anti-bot wall (detail = matched title/marker)
                  - timeout           network or page-load timeout
                  - runtime_error     unexpected exception (detail = class+msg)
                  - not_installed     fetcher dependency missing
    """
    log = _get_logger()
    log.info("scrape_jobs called sites={} keywords={}", sites, keywords)
    t_start = time.monotonic()

    try:
        config = _load_config(DEFAULT_CONFIG_PATH)
    except ConfigError as exc:
        log.error("scrape_jobs config error: {}", exc)
        return {"error": str(exc)}

    target_sites = list(sites) if sites else list(config.enabled_site_names())
    target_keywords = list(keywords) if keywords else list(config.keywords)

    # scrape in-process; results come back in memory (no output/ disk round-trip)
    exit_code, site_results = run_scraper(config, targets=target_sites, keywords=target_keywords)
    by_pair = {(r.keyword, r.site): r for r in site_results}

    # build raw (all jobs) + filtered (post-filter) payloads for Mongo, normalize
    # the filtered jobs for the response
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    filtered_results: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    for keyword in target_keywords:
        per_site: list[dict[str, Any]] = []
        for name in target_sites:
            site_result = by_pair.get((keyword, name))
            if site_result is None:
                errors.append(
                    {"keyword": keyword, "site": name, "reason": "scraper produced no result"}
                )
                continue
            raw_results.append({"keyword": keyword, "site": name, "payload": site_result.raw})
            payload = site_result.filtered
            filtered_results.append({"keyword": keyword, "site": name, "payload": payload})
            if isinstance(payload, dict) and "error" in payload:
                err: dict[str, Any] = {
                    "keyword": keyword,
                    "site": name,
                    "reason": str(payload.get("error")),
                }
                attempts = payload.get("attempts")
                if isinstance(attempts, list):
                    err["attempts"] = attempts
                errors.append(err)
                continue
            normalized_site = _normalize_site_payload(
                payload=payload, site_name=name, keyword=keyword
            )
            per_site.append(normalized_site)
        results.append({"keyword": keyword, "sites": per_site})

    total_jobs = sum(s.get("count", 0) for r in results for s in r.get("sites", []))
    note = _build_note(errors)
    result = {
        "ok": len(errors) == 0,
        "keywords": target_keywords,
        "requested_sites": target_sites,
        "exit_code": exit_code,
        "results": results,
        "errors": errors,
    }

    duration = time.monotonic() - t_start
    log.info(
        "scrape_jobs done ok={} errors={} jobs={} duration={:.1f}s",
        result["ok"],
        len(errors),
        total_jobs,
        duration,
    )

    _write_status(result, duration)

    # one document per run; the bot later patches it with Discord columns
    mongo_id: str | None = None
    try:
        mongo_id = mongo.insert_run(
            {
                "run_metadata": {
                    "ok": result["ok"],
                    "exit_code": exit_code,
                    "keywords": target_keywords,
                    "requested_sites": target_sites,
                    "errors": errors,
                    "per_site_counts": _build_per_site_counts(results),
                },
                "filtered_results": filtered_results,
                "raw_results": raw_results,
                "note": note,
            }
        )
        log.info("scrape_jobs: mongo insert ok id={}", mongo_id)
    except Exception as exc:
        log.opt(exception=True).error("scrape_jobs: mongo insert failed: {}", exc)
        # TODO: no durable fallback — a failed Mongo insert drops this run's
        # results entirely (the output/ disk persistence was retired). Add a
        # job-queue or event-log service to capture failed writes and replay
        # them, so a transient Mongo outage doesn't lose scraped data.

    # immutable: build a new dict rather than mutating `result` (already passed to _write_status)
    return {**result, "mongo_id": mongo_id}


def _build_app() -> Starlette:
    """Build the streamable-http ASGI app with a process-level shutdown hook.

    FastMCP wires ``FastMCP(lifespan=...)`` into the per-MCP-session low-level
    server — for the streamable-http transport that fires per client session,
    NOT when the process stops. To close shared resources on shutdown we compose
    the Starlette app's OWN lifespan (the session manager) with a mongo close.
    """
    app = mcp.streamable_http_app()
    inner = app.router.lifespan_context

    @asynccontextmanager
    async def _composed(starlette_app: Starlette) -> AsyncIterator[None]:
        log = _get_logger()
        log.info("mcp server starting up")
        try:
            async with inner(starlette_app):
                yield
        finally:
            log.info("mcp server shutting down; closing mongo client")
            mongo.close()

    app.router.lifespan_context = _composed
    return app


def main() -> None:
    import uvicorn

    _get_logger()  # configure loguru + install root InterceptHandler BEFORE uvicorn
    init_sentry()  # attach Sentry's loguru sink AFTER loguru is configured

    # Mirrors FastMCP.run_streamable_http_async (a thin uvicorn wrapper) but
    # serves OUR app with the composed lifespan so mongo.close() runs at shutdown.
    # log_config=None → uvicorn's loggers propagate to the root InterceptHandler
    # (loguru) instead of uvicorn installing its own handlers.
    uvicorn.run(
        _build_app(),
        host=HOST,
        port=PORT,
        log_level=mcp.settings.log_level.lower(),
        log_config=None,
    )


if __name__ == "__main__":
    main()
