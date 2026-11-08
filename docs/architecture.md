# Architecture

A short tour of how the pieces fit together. Helpful when proposing
config edits that touch unfamiliar areas, or when adding a new site.

## Package map

```
scraper/                    # CLI + library
├── __main__.py             # `python -m scraper [--config PATH] [--keyword KW] [sites...]`
├── runner.py               # orchestrates (keyword, site) pairs through a thread pool
├── config_loader.py        # settings dict → AppConfig dataclass + validation
├── job_settings.py         # JobSettingsStore: Mongo job settings, versions, history
├── seed_settings.py        # seeds Mongo from seeds/job_settings.yaml
├── types.py                # canonical Job TypedDict + CANONICAL_FIELDS
├── config.py               # static constants (USER_AGENT, CHALLENGE_MARKERS, etc.)
├── fetchers/               # HTTP layer
│   ├── base.py             # FetchChain, looks_like_challenge
│   ├── cloudscraper.py     # cheap HTTP fetcher (Cloudflare-aware)
│   └── playwright.py       # browser fallback (lazy import, ~280MB Chromium)
├── api/
│   └── locations.py        # fixed city list per site (label + API value) for the UI picker, served by get_config
└── sites/                  # per-site adapters
    ├── base.py             # Scraper abstract
    ├── _next_data.py       # __NEXT_DATA__ extraction helper
    ├── _dates.py           # parse_to_iso() — locale-aware date parsing
    ├── _filter.py          # project_jobs(), apply_filter()
    ├── jobstreet.py
    ├── glints.py
    ├── linkedin.py
    └── indeed.py

mcp_server/                 # MCP HTTP server
├── server.py               # FastMCP, tools: list_sites, get_config, update_config, get_config_history, restore_config, get_scrape_status, test_proxy_connection, scrape_jobs
└── __init__.py             # (empty)
```

## Scraper UI API (`ui_server/`)

- `GET /api/config`: the job settings plus `location_options`, the same
  `{site: [{label, value}]}` map `get_config` returns.
- `GET /api/runs/{id}`: the run record plus `payloads`, a list of
  `{keyword, site, raw, filtered}` (`raw` / `filtered` are `null` when that
  side was not stored). Pairs from the run's keywords and sites come first,
  any other stored pair follows. Runs made before payloads were stored return `[]`.
  The data comes from `scrape_jobs` called with `include_payloads: true`.

## Request flow (per scrape run)

```
config.yaml   seeds/job_settings.yaml → Mongo `job_settings`
   │
   ▼
load_app_config()   →   AppConfig (immutable dataclass)
   │
   ▼
runner.run(config, targets, keywords)
   │
   ├─ build (keyword, site) cross-product list
   │
   ├─ for each pair (in ThreadPoolExecutor with concurrency cap):
   │   │
   │   ├─ scrape_cls(url=site.url_for(keyword), limit=config.limit)
   │   │
   │   ├─ FetchChain.fetch(url)
   │   │     ├─ CloudscraperFetcher (cheap, first attempt)
   │   │     │     └─ if challenge page or 4xx → fall through
   │   │     └─ PlaywrightFetcher (browser, ~280MB)
   │   │
   │   ├─ Scraper.parse(html)         → list[Job] (per-site selectors)
   │   ├─ runner._enrich_jobs()        → stamp matched_keyword + parse posted_at
   │   ├─ runner._within_max_age()     → drop stale jobs
   │   ├─ apply_filter()               → drop content-mismatch jobs
   │   └─ project_jobs(fields)         → strip to configured fields
   │
   └─ write output/<keyword-slug>/<site>.json
```

## Lifecycle of a Job dict

1. **Created** by `empty_job(site, title, company)` in the site's `parse()`.
   All canonical keys present, mostly `None`.
2. **Populated** by site-specific selectors / JSON walks in `parse()`.
3. **Enriched** by the runner: `matched_keyword`, `posted_at` (parsed UTC).
4. **Filtered** by max-age, then content filter.
5. **Projected** to the configured fields list — extra keys dropped.
6. **Serialized** as one entry in the per-site output JSON.

Steps 3 and 4 happen on the in-memory dict before projection, so even
fields you didn't configure still drive the filter.

## Concurrency model

- One `ThreadPoolExecutor` per `runner.run()` call, sized to `min(config.concurrency, len(pairs))`.
- Each worker thread builds its own Playwright `sync_playwright()` context
  when needed — never share the instance across threads.
- cloudscraper sessions are created per call (not reused), so they're
  thread-safe by virtue of being thread-local.
- Output writes go to different files (`output/<slug>/<site>.json`) per
  thread, so no inter-thread file contention.

## URL templating

Each site's `url_template` substitutes one of three placeholders before
fetching:

| Placeholder       | Format                          |
|-------------------|---------------------------------|
| `{keyword}`       | URL-encoded space               |
| `{keyword_slug}`  | lowercase + hyphens             |
| `{keyword_plus}`  | plus-separated                  |

Resolution happens in `SiteConfig.url_for(keyword)`. Validation runs at
config load time (`parse()` formats with a sample keyword and rejects
unknown placeholders) so a bad template fails loudly on startup, not
mid-scrape.

## Output JSON shape

```json
{
  "keyword": "software engineer",
  "fields": ["company", "location", "matched_keyword", "posted_at", "site", "title", "url"],
  "max_age_hours": 24,
  "filter": {"location": ["jakarta"]},
  "count": 2,
  "jobs": [
    {
      "site": "jobstreet",
      "matched_keyword": "software engineer",
      "title": "...",
      "company": "...",
      "url": "...",
      "location": "Jakarta Selatan",
      "posted_at": "2026-05-09T03:25:21+00:00"
    },
    ...
  ]
}
```

`fields` lists what was actually emitted (post-projection). `count` is
the post-filter, post-projection count. `jobs[*]` only contains keys that
were in `fields` (plus the always-on anchors).

## MCP layer relationship

`mcp_server/server.py` is a thin shell over `scraper.runner.run` and
`scraper.job_settings.load_app_config`. It does no business logic of its own — every
tool delegates to the same code paths the CLI uses, so MCP behavior
matches `python -m scraper` exactly.

`update_config` and `restore_config` are the mutating tools. Both validate
with the same parser (`config_loader.parse`) before writing to Mongo.
See [`mcp.md`](mcp.md) for tool details.

## Where extension lives

| Want to add… | Touch |
|--------------|-------|
| A new site | `scraper/sites/<name>.py` + register in `sites/__init__.py::SCRAPERS`; add the `sites.<name>` entry to `seeds/job_settings.yaml` and to each environment with `update_config` |
| A new canonical field | `scraper/types.py` (Job + CANONICAL_FIELDS), per-site parsers fill it, optionally update `default_fields` |
| A new fetcher (e.g. proxy, undetected-chromedriver) | `scraper/fetchers/<name>.py`; insert into `runner.default_fetch_chain()` |
| A new MCP tool | `mcp_server/server.py`; mark with `@mcp.tool()` |
| A new filter key | `scraper/config_loader.py::FILTERABLE_FIELDS` + update Job extractors so the field is reliably populated |

The boundaries are explicit: site adapters know nothing about HTTP,
fetchers know nothing about parsing, config knows nothing about runtime.
Keep that split.
