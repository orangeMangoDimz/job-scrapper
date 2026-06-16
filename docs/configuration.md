# Configuration reference

The runtime is driven entirely by `config.yaml` at the repo root. The loader
(`scraper/config_loader.py::load`) parses, validates, and resolves the file
into an `AppConfig` dataclass. Any malformed value raises `ConfigError` and
the run aborts — partial writes never reach disk.

This page documents every key the loader recognizes. For filter semantics
specifically, see [`filters.md`](filters.md).

## Top-level keys

```yaml
keywords: [software engineer, data analyst]   # required
limit: 2                                       # optional, default 2
concurrency: 2                                 # optional, default 2
output_dir: output                             # optional, default 'output'
max_age_hours: 24                              # optional, no default = no filter
default_fields: [...]                          # optional, default 4 fields
filter: {...}                                  # optional, no default = no filter
sites: {...}                                   # required, non-empty
```

### `keywords` (required)

List of strings. Each keyword is run against every enabled site, producing
a `(keyword, site)` cross-product. Output lands under
`output/<keyword-slug>/<site>.json`.

- Backwards-compatible alias: `keyword: <string>` is accepted and treated as
  a single-element list.
- Empty strings are rejected. Duplicates are silently de-duped.
- Each keyword is templated into the URL via `{keyword}`, `{keyword_slug}`,
  or `{keyword_plus}` (see "Site URL templating" below).

```yaml
# Multi-keyword
keywords:
  - software engineer
  - data analyst

# Single keyword (legacy form)
keyword: backend developer
```

### `limit` (optional, default `2`)

Integer, must be `>= 1`. Maximum number of jobs each site emits per
`(keyword, site)` pair.

```yaml
limit: 5
```

### `concurrency` (optional, default `2`)

Integer, must be `>= 1`. Maximum number of `(keyword, site)` pairs running
in parallel through a thread pool.

- `concurrency: 1` falls back to a sequential loop (no thread overhead).
- Each Playwright fallback consumes ~250-300MB RAM. Tune for available memory.

```yaml
concurrency: 4
```

### `output_dir` (optional, default `output`)

String path. Where per-site JSON files land. Resolved relative to the
working directory if not absolute.

```yaml
output_dir: ./scraper-output
```

### `max_age_hours` (optional, no default)

Integer, must be `>= 1` if set. Drops jobs whose parsed `posted_at` is
older than this many hours from now (UTC). Jobs with unparseable
`posted_date` are kept (conservative).

- Per-site override: `sites.<name>.max_age_hours` replaces the global.
- Pair this with the URL templates' server-side recency params for best results
  (e.g. jobstreet `?daterange=1`, linkedin `&f_TPR=r86400`, indeed `&fromage=1`).
  See `sites.md` for the full per-site param table.

```yaml
max_age_hours: 24
```

### `default_fields` (optional)

List of canonical field names to emit per Job. Default:
`[title, company, location, url]`.

Allowed canonical fields:

```
site                matched_keyword     title             company
url                 location            salary            posted_date
posted_at           work_type           employment_type   experience_level
job_id              requirements
```

- `site`, `matched_keyword`, `title`, `company`, `url` are **always
  included** regardless of this list (anchors).
- Unknown field names log a warning and are silently dropped — they don't
  abort the load.
- Per-site override: `sites.<name>.fields` replaces the global list.

```yaml
default_fields:
  - title
  - company
  - location
  - url
  - salary
  - posted_date
  - posted_at
```

### `filter` (optional)

Content filter applied after recency, before field projection. Each value
can be a single string or a list. Substring + case-insensitive.

See [`filters.md`](filters.md) for full reference.

```yaml
filter:
  location: [jakarta, bandung]
  employment_type: [full-time, internship]
  work_type: [remote, hybrid]
```

### `sites` (required)

Mapping from site-name → site config. Site name must match a registered
scraper in `scraper/sites/__init__.py::SCRAPERS`. Currently supported:

- `jobstreet`
- `glints`
- `linkedin`
- `indeed`

Each site entry:

```yaml
sites:
  <name>:
    enabled: true                                  # optional, default true
    url_template: "https://...?{keyword}..."       # required
    fields: [...]                                  # optional, overrides default_fields
    max_age_hours: 12                              # optional, overrides global
    filter: {...}                                  # optional, replaces global
    limit: 10                                      # optional, overrides global limit
```

#### `sites.<name>.enabled`

Boolean. Disabled sites are skipped during default runs. CLI args
(`python -m scraper jobstreet`) override and run regardless of this flag.

#### `sites.<name>.url_template`

String. The URL fetched per `(keyword, site)` pair. Three placeholders are
substituted:

| Placeholder       | Format                          | Example for `software engineer` |
|-------------------|---------------------------------|---------------------------------|
| `{keyword}`       | URL-encoded space (`%20`)       | `software%20engineer`           |
| `{keyword_slug}`  | lowercase + hyphens             | `software-engineer`             |
| `{keyword_plus}`  | plus-separated                  | `software+engineer`             |

Pick the one that matches the site's URL convention. The loader validates
all placeholders against this allowlist; unknown placeholder → `ConfigError`.

```yaml
sites:
  jobstreet:
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs?daterange=1"
  indeed:
    url_template: "https://id.indeed.com/jobs?q={keyword_plus}&l=Indonesia&fromage=1"
```

#### `sites.<name>.fields`

Optional list of canonical field names. Replaces (does not merge into)
`default_fields` for this site only. Same validation as `default_fields`.

#### `sites.<name>.max_age_hours`

Optional integer. Replaces the global `max_age_hours` for this site only.

#### `sites.<name>.filter`

Optional dict. Replaces (does not merge into) the global `filter` block for
this site only. Same shape as the global filter — see [`filters.md`](filters.md).

#### `sites.<name>.limit`

Optional positive integer. Replaces the global `limit` for this site only —
useful when one source's relevance ranking buries good matches deep in the
list (e.g. raise `sites.indeed.limit` so Jakarta jobs surface past the top
two non-Jakarta hits, while keeping other sites at the cheaper global limit).

## Validation rules summary

The loader (`load(path)`) enforces:

| Key                       | Rule                                             | On failure        |
|---------------------------|--------------------------------------------------|-------------------|
| `keywords` / `keyword`    | At least one non-empty string                    | `ConfigError`     |
| `limit`                   | Integer >= 1                                     | `ConfigError`     |
| `concurrency`             | Integer >= 1                                     | `ConfigError`     |
| `max_age_hours`           | Integer >= 1 or null                             | `ConfigError`     |
| `sites`                   | Non-empty mapping                                | `ConfigError`     |
| `sites.<name>.url_template` | Non-empty string with valid placeholders only  | `ConfigError`     |
| `default_fields` entries  | Strings; unknown names → warning, dropped       | `[config] warning` (load continues) |
| `filter` keys             | One of `location`, `employment_type`, `work_type`; unknown → warning, dropped | `[config] warning` |
| `filter` values           | String or list-of-strings                        | `ConfigError`     |


## Proxy configuration

Route HTTP requests through a proxy server. Useful for bypassing datacenter IP blocks by using residential IPs.

```yaml
proxy: "socks5://localhost:1080"
```

### Supported proxy formats

| Format | Example | Use case |
|--------|---------|----------|
| SOCKS5 | `socks5://localhost:1080` | SSH tunnels, residential proxies |
| HTTP | `http://proxy.example.com:8080` | Corporate proxies |
| HTTPS | `https://proxy.example.com:8080` | Secure corporate proxies |
| Auth | `socks5://user:pass@host:1080` | Authenticated proxies |

### Common setup: SSH tunnel

On VPS (remote server), create SOCKS5 tunnel to your home machine:

```bash
# From VPS, connect to your home machine
ssh -D 1080 -f -N user@your-home-ip

# Test proxy works
curl --socks5 localhost:1080 http://httpbin.org/ip
# Should show your home IP, not VPS IP
```

Then in `config.yaml`:
```yaml
proxy: "socks5://localhost:1080"
```

### Docker considerations

When using `--network host` mode (required for localhost proxy):
- Container shares host network stack
- `localhost:1080` inside container = `localhost:1080` on VPS host
- No port mapping needed

### Environment variable override

Set `PROXY_URL` environment variable to override config file:

```bash
PROXY_URL="socks5://localhost:1080" python -m scraper
```

### Disable proxy

Comment out or remove the `proxy` key:
```yaml
# proxy: "socks5://localhost:1080"
```

## Environment variables

Deploy-time knobs that override or extend `config.yaml`. All are optional unless
marked **required**. Managed in `scraper/settings.py` (Mongo + logging) and the
bot entrypoint/run scripts.

| Variable | Default | Component | Effect |
|---|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017` (compose derives from `MONGO_ROOT_*`) | mcp + scraper | Mongo connection string |
| `MONGO_DB_NAME` | `job_scraper` | mcp + scraper | Database name |
| `MONGO_COLLECTION_NAME` | `scrape_runs` | mcp | Run-history collection |
| `MONGO_SERVER_SELECTION_TIMEOUT_MS` | `3000` | mcp + scraper | Fast-fail Mongo selection timeout |
| `LOG_LEVEL` | `INFO` | mcp + scraper | Log level (DEBUG\|INFO\|WARNING\|ERROR) |
| `LOG_FORMAT` | `json` | mcp + scraper | Log format: `json` (loguru-native `serialize` envelope) or `plain` |
| `LOG_FILE` | _(empty)_ | mcp + scraper | Opt-in rotating file path; empty = stdout only |
| `LOG_FILE_MAX_BYTES` | `5242880` | mcp + scraper | Rotation size in bytes |
| `LOG_FILE_BACKUP_COUNT` | `3` | mcp + scraper | Number of rotation backups kept |
| `STATUS_FILE` | `logs/status.json` | mcp | Run-status snapshot path |
| `SENTRY_ENABLED` | `false` | mcp | Toggle Sentry error monitoring on/off (empty = false) |
| `SENTRY_DSN` | _(empty)_ | mcp | Sentry project DSN (**secret**); required when `SENTRY_ENABLED=true` |
| `SENTRY_ENVIRONMENT` | `production` | mcp | Sentry environment tag |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0` | mcp | Perf-trace sample rate; `0.0` = errors only |
| `SENTRY_RELEASE` | _(empty)_ | mcp | Optional release/version tag (CI sets the commit SHA) |
| `MCP_HOST` | `0.0.0.0` | mcp | Bind host |
| `MCP_PORT` | `8080` | mcp | Bind port |
| `SCRAPER_CONFIG` | `config.yaml` | mcp | Config file path |
| `PROXY_TEST_URL` | `https://api.ipify.org?format=json` | mcp | Proxy-test target URL |
| `PROXY_TEST_TIMEOUT_SEC` | `25` | mcp | Proxy-test request timeout |
| `BOT_SCHEDULE` | _(empty → `config.yaml` → `0 11 * * *`)_ | bot | Cron schedule; resolved at container start, no rebuild needed |
| `CLAUDE_MODEL` | _(empty → `config.yaml` → `claude-haiku-4-5-20251001`)_ | bot | Claude model for the cron run |
| `BOT_LOG_FILE` | _(empty)_ | bot | Opt-in cron-log file path; empty = stdout only |
| `TZ` | `Asia/Jakarta` | bot | Container timezone |
| `CLAUDE_CONFIG_DIR` / `CLAUDE_CONFIG_FILE` | _(host paths)_ | bot | Mounted Claude config paths |
| `DISCORD_BOT_TOKEN` | **required** | bot | Discord bot application token |
| `DISCORD_CHANNEL_ID` | **required** | bot | Discord channel ID for job posts |
| `MONGO_ROOT_USER` | `admin` | mongo | Init username |
| `MONGO_ROOT_PASSWORD` | **required** | mongo | Init password |

> Logging runs through **loguru** as a single STDOUT stream by default (Factor XI),
> emitting **JSON** (loguru-native `serialize` envelope; set `LOG_FORMAT=plain` for
> human-readable lines). `docker logs` captures everything — including uvicorn,
> FastMCP, and pymongo, which are routed into loguru via a root intercept handler.
> Set `LOG_FILE` (scraper-mcp) or `BOT_LOG_FILE` (bot) to opt into a rotating file
> alongside stdout.

> **Sentry (error monitoring)** is **off by default**. Set `SENTRY_ENABLED=true`
> plus a `SENTRY_DSN` to activate it on `scraper-mcp` (only that service is
> instrumented — the cron bot's scraping runs through it). Capture rides on loguru;
> genuine errors get stack traces while routine scrape soft-failures (anti-bot
> walls, fetcher fall-through) are filtered out. Errors-only by default
> (`SENTRY_TRACES_SAMPLE_RATE=0.0`). The DSN is a **secret** — keep it in `.env`
> locally / a GitHub secret in prod, never in `config.yaml`. Wiring lives in
> `scraper/observability.py`.

## New `config.yaml` keys

### `bot.model` (optional)

String. The Claude model the cron bot uses. Overridable at runtime by the
`CLAUDE_MODEL` environment variable — no image rebuild needed.

```yaml
bot:
  model: claude-haiku-4-5-20251001
```

### `timeouts` (optional)

All timeout keys are optional; omitted keys use the listed defaults.

| Key | Default | Effect |
|---|---|---|
| `http_seconds` | `30` | HTTP request timeout for non-Playwright fetches |
| `playwright_goto_ms` | `60000` | Playwright `page.goto()` timeout in ms |
| `playwright_networkidle_ms` | `15000` | Playwright network-idle wait in ms |
| `playwright_settle_seconds` | `2` | Post-idle settle delay in seconds |
| `indeed_api_seconds` | `30` | Indeed API request timeout in seconds |

```yaml
timeouts:
  http_seconds: 30
  playwright_goto_ms: 60000
  playwright_networkidle_ms: 15000
  playwright_settle_seconds: 2
  indeed_api_seconds: 30
```

## Loading the resolved config

```python
from pathlib import Path
from scraper.config_loader import load

config = load(Path("config.yaml"))

config.keywords           # tuple[str, ...]
config.limit              # int
config.concurrency        # int
config.output_dir         # Path
config.default_fields     # tuple[str, ...]
config.max_age_hours      # int | None
config.filter             # dict[str, list[str]]
config.sites              # tuple[SiteConfig, ...]

config.fields_for("glints")    # frozenset[str]
config.max_age_for("glints")   # int | None
config.filter_for("glints")    # dict[str, list[str]]
```

## Live editing via MCP

The MCP server exposes `update_config` for safe runtime patching. See
[`mcp.md`](mcp.md) for the tool catalog and patch shape.

The patch path is preferred over direct file edits because the merged
result is validated through this same loader before being written to disk;
invalid patches return an error and leave the live file untouched.
