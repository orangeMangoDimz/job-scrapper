# Runbook — common config edits

How to translate user requests into `update_config` patches. Each recipe
shows the exact tool call so you can copy-paste-modify.

The general loop is always:

1. `get_config` → see current shape
2. Compose a minimal patch
3. `update_config` with that patch and the version from `get_config`
4. On `ok=false`, surface the `message` verbatim

For schema details see [`configuration.md`](configuration.md).
For the tool catalog see [`mcp.md`](mcp.md).

## "Search for a different role"

User: "switch the search to data analyst" / "add backend developer to the keywords"

```json
{"patch": {"keywords": ["data analyst"]}}
```

Or to add without losing existing:

```json
{"patch": {"keywords": ["software engineer", "backend developer"]}}
```

Note: `keywords` is a list — patches replace the list, they do not append.
Always include all desired keywords in the new patch.

## "Only show jobs from last X hours"

User: "tighten to last 6 hours" / "show me last week's jobs"

```json
{"patch": {"max_age_hours": 6}}
```

Pair with URL params if you also want server-side filtering. See
[`sites.md`](sites.md) for the param table per site. Example for last
week (jobstreet + linkedin):

```json
{"patch": {
  "max_age_hours": 168,
  "sites": {
    "jobstreet": {"url_template": "https://id.jobstreet.com/id/{keyword_slug}-jobs?daterange=7"},
    "linkedin":  {"url_template": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keyword}&location=Indonesia&f_TPR=r604800&start=0"}
  }
}}
```

## "Disable / re-enable a site"

User: "stop scraping LinkedIn" or "Glints is being noisy, turn it off"

```json
{"patch": {"sites": {"linkedin": {"enabled": false}}}}
```

To re-enable:

```json
{"patch": {"sites": {"linkedin": {"enabled": true}}}}
```

## "Filter jobs to a specific location"

User: "only Jakarta" / "Jakarta or Bandung please"

```json
{"patch": {"filter": {"location": ["jakarta", "bandung"]}}}
```

Substring + case-insensitive — `jakarta` catches Jakarta Barat, Jakarta
Selatan, Area DKI Jakarta, etc. See [`filters.md`](filters.md) for full
filter semantics.

## "Only internships" or "no internships"

User: "internships only" / "exclude internships, full-time only"

Internships only:
```json
{"patch": {"filter": {"employment_type": "internship"}}}
```

Full-time only:
```json
{"patch": {"filter": {"employment_type": "full-time"}}}
```

Note: `employment_type` is reliably populated only by Glints. Other sites
emit null and pass via the conservative null-rule. The filter mainly
narrows Glints' output.

## "Remote-friendly only"

User: "remote work only" / "remote or hybrid is fine"

```json
{"patch": {"filter": {"work_type": ["remote", "hybrid"]}}}
```

Same coverage caveat as `employment_type` — Glints reliably emits
`work_type`, others don't.

## "Increase / decrease how many jobs per site"

User: "give me 10 per site instead of 2" / "lower to 1, this is too noisy"

```json
{"patch": {"limit": 10}}
```

Higher `limit` increases scrape time and block risk. Tighten
`max_age_hours` or filters at the same time to keep output relevant.

## "Speed it up" / "slow it down"

User: "scrape faster" or "running too hot, slow it down"

`concurrency` is not a job setting, so `update_config` refuses it. Change
`concurrency` in `config.yaml` and rebuild the images.

Each Playwright fallback consumes ~250-300MB RAM. On a 2GB host, stay at
2; on a bigger host, 4 is safe.

## "Reset the filter"

User: "drop the filter, show everything"

```json
{"patch": {"filter": null}}
```

`null` clears the filter. To clear a single key, send the remaining keys
without the one to drop:

```json
{"patch": {"filter": {"location": ["jakarta"]}}}
```

(Removes `employment_type` and `work_type` if they were set.)

## "Apply a per-site override"

User: "Glints should only show internships" (while global filter stays
permissive)

```json
{"patch": {"sites": {"glints": {"filter": {"employment_type": "internship"}}}}}
```

Per-site `filter` blocks REPLACE the global block (no merge across
the boundary). Once a per-site filter is set, the global filter doesn't
apply to that site at all. A site with `filter: {}` has no filter. To go back
to the global filter, send `null`:

```json
{"patch": {"sites": {"glints": {"filter": null}}}}
```

## "Add new fields to the output"

User: "include posted_at and salary in the JSON"

Globally:
```json
{"patch": {"default_fields": ["title", "company", "location", "url", "salary", "posted_date", "posted_at"]}}
```

For one site only:
```json
{"patch": {"sites": {"linkedin": {"fields": ["title", "company", "location", "url", "posted_date", "posted_at"]}}}}
```

`site`, `matched_keyword`, `title`, `company`, `url` are anchors and always
appear regardless of this list.

## "Run an ad-hoc scrape without saving config"

User: "just run it once for 'fullstack engineer'" — no config persist

Skip `update_config` entirely; use `scrape_jobs` with explicit args:

```json
{"keywords": ["fullstack engineer"], "sites": ["linkedin", "jobstreet"]}
```

The saved job settings are unchanged; only the run is overridden. Add `"save_run": false`
to keep the run out of MongoDB as well.

## "Show me the current settings"

```json
// no patch needed
"call_tool": "get_config"
```

For a higher-level view (resolved sample URLs, enabled list):

```json
"call_tool": "list_sites"
```

## When validation fails

`update_config` returns `{ok: false, reason: "<kind>", message: "<text>"}`. `reason` is `invalid`, `conflict`, or `unavailable`. Common `message` values for `invalid`:

| Error fragment                                    | Cause                                              |
|---------------------------------------------------|----------------------------------------------------|
| `'limit' must be >= 1`                            | Sent `0` or negative integer                       |
| `not a job setting: concurrency`                  | Sent `concurrency` or `proxy`, which are not job settings |
| `'max_age_hours' must be a positive integer`      | Sent `0`, negative, or non-integer                 |
| `'keywords' must be a non-empty list of strings`  | Empty list or non-string entries                   |
| `url_template uses unknown placeholder ...`       | URL has `{x}` not in `keyword/keyword_slug/keyword_plus` |
| `filter.<key>.<subkey> must be a string or list` | Sent a number, dict, or other non-string value     |

When you see these, don't loop blindly. Surface the verbatim `message` to the
user and ask how to proceed (or whether to drop the offending key).

## Version history

Every save keeps the old version in `job_settings_history`, last 20 kept. To
roll back, use **Restore** on `/config`, or call `restore_config` with the
version from `get_config_history`. A restore creates a new version, so it can
be undone the same way.
