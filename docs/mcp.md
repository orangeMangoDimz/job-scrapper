# MCP server

`mcp_server/server.py` exposes the scraper as a Model Context Protocol server
over streamable HTTP (default `0.0.0.0:8080`). External Claude sessions
register it and call its tools to inspect, modify, and run the scraper without
shelling into the container.

This page is the canonical reference for what those tools accept and return.

## Boot

```bash
python -m mcp_server.server          # local
docker compose up -d scraper-mcp     # container (orchestration repo)
```

Environment variables:

| Var               | Default       | Purpose                                 |
|-------------------|---------------|-----------------------------------------|
| `MCP_HOST`        | `0.0.0.0`     | Bind address                            |
| `MCP_PORT`        | `8080`        | Bind port                               |
| `SCRAPER_CONFIG`  | `config.yaml` | Path to the machine settings file (`concurrency`, `output_dir`, `bot`) |
| `SCRAPER_PROXY_URL` | none, required | Proxy URL for scrapes. Empty means direct connection. Not set stops scrapes |
| `PROXY_TEST_URL`  | `https://api.ipify.org?format=json` | URL `test_proxy_connection` fetches by default |
| `PROXY_TEST_TIMEOUT_SEC` | `25` | Per-request timeout for that probe |

## Registering from a client Claude session

Add an entry to that container's `~/.claude/.mcp.json`:

```json
{
  "mcpServers": {
    "job-scraper": {
      "type": "http",
      "url": "http://scraper-mcp:8080/mcp"
    }
  }
}
```

Hostname `scraper-mcp` assumes both containers share the same Docker network.
Adjust if running elsewhere.

## Tool catalog

### `list_sites`

Read-only. Inspect resolved config without running anything.

**Args**: none.

**Returns**:

```json
{
  "keywords": ["software engineer", "data analyst"],
  "limit": 2,
  "sites": [
    {
      "name": "jobstreet",
      "enabled": true,
      "url_template": "https://id.jobstreet.com/id/{keyword_slug}-jobs?daterange=1",
      "sample_url": "https://id.jobstreet.com/id/software-engineer-jobs?daterange=1"
    },
    ...
  ]
}
```

Use this first to confirm what `keywords` and which `sites` are active before
calling `scrape_jobs` or proposing a `update_config` patch.

### `get_config`

Read-only. Returns the job settings from Mongo, with their version.

**Args**: none.

**Returns**:

```json
{
  "version": 4,
  "updated_at": "2026-11-02T01:00:00+00:00",
  "updated_by": "ui",
  "settings": {
    "keywords": ["software engineer"],
    "limit": 2,
    "max_age_hours": 24,
    "filter": {"location": ["jakarta"]},
    "sites": {}
  },
  "job_fields": ["site", "matched_keyword", "title", "..."],
  "mandatory_fields": ["site", "matched_keyword", "title", "company", "url"]
}
```

- `job_fields`: every field name `default_fields` and `sites.<name>.fields` accept, in scraper order
- `mandatory_fields`: fields saved for every job whatever the settings say

Returns `{"error": "..."}` when Mongo is down or the document is missing.

Always call `get_config` before `update_config` to know the current shape so
your patch is minimal.

### `get_scrape_response_structure`

Read-only. Returns canonical response contract for `scrape_jobs`.

**Args**: none.

**Returns**:

```json
{
  "tool": "scrape_jobs",
  "version": "1.0.0",
  "job_fields": ["site", "matched_keyword", "title", "..."],
  "top_level_fields": ["ok", "keywords", "requested_sites", "exit_code", "results", "errors"],
  "site_result_fields": ["site", "keyword", "fields", "max_age_hours", "filter", "count", "jobs"],
  "error_fields": ["keyword", "site", "reason", "attempts"],
  "sample": { "...": "example payload" }
}
```

Use this when you need strict output formatting in downstream automations.

### `update_config`

Write. Applies a patch to the job settings, validates the result, and keeps the old version in history.

**Args**:

```json
{ "patch": { }, "expected_version": 4, "source": "mcp" }
```

- `patch`: top-level keys are replaced whole. `sites` merges by site name. Each field of a site is replaced whole, so send the full `filter` or `api`. A `null` removes the key, so a site field goes back to the global value
- `expected_version`: optional. The version you read. A mismatch saves nothing
- `source`: `ui` or `mcp`. Kept with the version

Only job setting keys are allowed. `proxy` and `concurrency` are refused. Field names in `default_fields` or `sites.<name>.fields` that are not in `get_config`'s `job_fields` are refused with reason `invalid`.

**Returns** (success):

```json
{ "ok": true, "version": 5, "updated_at": "...", "updated_by": "mcp", "settings": { } }
```

**Returns** (failure, nothing changed):

```json
{ "ok": false, "reason": "invalid", "message": "'limit' must be >= 1, got -5" }
```

`reason` is `invalid`, `conflict`, or `unavailable`.

### `get_config_history`

Read-only. Returns up to 20 older versions, newest first.

```json
{ "entries": [ { "version": 3, "updated_at": "...", "updated_by": "seed", "keywords": ["..."], "enabled_sites": ["upwork"] } ] }
```

### `restore_config`

Write. Makes an older version current. The restore creates a new version, so it can be undone.

**Args**: `version`, `expected_version`, and optional `source`.

**Returns**: same shape as `update_config`.

#### Patch examples

Change keyword:
```json
{"patch": {"keywords": ["data analyst"]}}
```

Tighten recency:
```json
{"patch": {"max_age_hours": 6}}
```

Disable LinkedIn for the next runs:
```json
{"patch": {"sites": {"linkedin": {"enabled": false}}}}
```

Add a new search location to the filter (the whole list is replaced, so send every location):
```json
{"patch": {"filter": {"location": ["jakarta", "bandung", "surabaya"]}}}
```

Per-site filter override (replaces the whole filter of that site):
```json
{"patch": {"sites": {"glints": {"filter": {"employment_type": "internship"}}}}}
```

Return a site field to the global value:
```json
{"patch": {"sites": {"glints": {"max_age_hours": null}}}}
```

Replace LinkedIn URL template (e.g. switch to a different geoId):
```json
{"patch": {"sites": {"linkedin": {"url_template": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keyword}&geoId=104884688&f_TPR=r86400&start=0"}}}}
```

#### Validation

Every patch is merged, then run through `scraper.config_loader.parse` before
anything is saved. The same rules listed in
[`configuration.md`](configuration.md) apply: malformed `limit`, missing
required keys, invalid URL placeholders, etc. all return
`{ok: false, reason: "invalid", message: …}`.

### `test_proxy_connection`

Read-only network probe. Performs one HTTPS GET through the proxy using the
same curl_cffi stack as the scraper fetchers (so HTTP, HTTPS, and SOCKS5 proxy
URLs work the same as in a scrape).

**Args** (all optional):

```json
{
  "proxy_url": "socks5://127.0.0.1:1080",
  "url": "https://api.ipify.org?format=json"
}
```

- `proxy_url`: when omitted, uses `SCRAPER_PROXY_URL`. If both are missing,
  returns `{ok: false, error: ...}`.
- `url`: target URL to fetch (must be `http` or `https`). Default comes from
  `PROXY_TEST_URL` or ipify as in the env table above.

**Returns** (success example):

```json
{
  "ok": true,
  "proxy_redacted": "user:***@proxy.example.com:1080",
  "source": "config",
  "test_url": "https://api.ipify.org?format=json",
  "duration_ms": 842.5,
  "http_status": 200,
  "egress_ip": "203.0.113.1",
  "response_excerpt": "{\"ip\":\"203.0.113.1\"}"
}
```

`proxy_redacted` masks proxy passwords. `source` is present only when the
proxy URL came from `SCRAPER_PROXY_URL`. On failure, `ok` is false and `error` describes
validation, connection, or non-200 HTTP.

The `docs:/app/docs:ro` mount makes the markdown reference docs (this file,
`runbook.md`, `configuration.md`, `sites.md`, etc.) live-readable from inside
the container. Edit any doc on the host and the next read inside the
container sees it — no rebuild needed. Drop the mount for production
deployments where docs aren't expected to change at runtime.

### `scrape_jobs`

Run the scraper. Triggers fetches across `(keyword, site)` pairs and returns
aggregated results.

**Args** (all optional):

```json
{
  "sites": ["linkedin", "indeed"],
  "keywords": ["data analyst"],
  "save_run": true
}
```

- `sites`: list of site names to scrape. Omitted = all enabled sites.
- `keywords`: list of keywords to scrape. Omitted = all configured keywords.
- `save_run`: store the run in MongoDB. Omitted = `true`. The job-match search
  box and the scraper UI send `false`, so their results are shown once and stay
  out of the scrape history. `mongo_id` is then `null`.

**Returns**:

```json
{
  "keywords": ["data analyst"],
  "requested_sites": ["linkedin", "indeed"],
  "exit_code": 0,
  "results": [
    {
      "keyword": "data analyst",
      "sites": [
        {
          "site": "linkedin",
          "fields": ["title", "company", "url", ...],
          "max_age_hours": 24,
          "filter": {"location": ["jakarta"]},
          "count": 2,
          "jobs": [...]
        },
        {"site": "indeed", ...}
      ]
    }
  ],
  "errors": [
    {"keyword": "data analyst", "site": "glints", "reason": "fetch failed"}
  ]
}
```

`results` is always grouped by keyword first, then site. `errors` collects
any pair whose JSON couldn't be read or whose fetch failed.

When the job settings cannot be loaded (Mongo is down, the document is missing, or `SCRAPER_PROXY_URL` is not set), `scrape_jobs` returns `{"ok": false, "error": "..."}` and scrapes nothing.

## Operational rules for Claude callers

When asked to change scraper behavior at runtime, follow this loop:

1. Call `get_config` (or `list_sites` for a higher-level view).
2. Construct a minimal `patch` reflecting only the user's request.
3. Call `update_config` with that patch and the version from `get_config`.
4. If `ok=false`, surface the `message` to the user — do NOT retry with a
   different patch unless the user agrees. The error is from the same
   validator the scraper itself uses.
5. On success, optionally call `scrape_jobs` to confirm the new config
   produces expected output.

Avoid:

- Sending a full `config` object as a "replacement" — always patch.
- Inventing keys not in [`configuration.md`](configuration.md).
- Modifying URL templates without checking [`sites.md`](sites.md) for the
  site's expected query-param vocabulary.
- Silently retrying on validation errors.

For specific edit recipes (most common user requests mapped to exact
patches), see [`runbook.md`](runbook.md).
