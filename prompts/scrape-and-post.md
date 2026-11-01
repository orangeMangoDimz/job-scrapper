# Multi-site job scrape

Execute all steps below now, in order. Do not ask for confirmation.

## Step 1 — Run the scraper

Call the `job-scraper` MCP tool `scrape_jobs` with no arguments. It will run
every enabled site for every configured keyword, applying the recency and
content filters from the job settings in Mongo, and return aggregated results.

The response shape is:

```json
{
  "keywords": ["software engineer", "data analyst"],
  "requested_sites": ["jobstreet", "glints", "linkedin", "indeed", "upwork"],
  "exit_code": 0,
  "results": [
    {
      "keyword": "software engineer",
      "sites": [
        {"site": "jobstreet", "fields": [...], "count": N, "jobs": [...]},
        ...
      ]
    },
    ...
  ],
  "errors": [{"keyword": "...", "site": "...", "reason": "..."}],
  "mongo_id": "<MongoDB _id of this run's document, or null if Mongo was unreachable>"
}
```

If `exit_code != 0` or `errors` is non-empty, include a one-line
diagnostic at the top of the Discord output. Continue and post whatever
jobs DID land — partial output beats silence.

## Step 2 — Pull formatting config

Read these from `/workspace/config.yaml` using `yq` (already in PATH):

```sh
TEMPLATE="$(yq -r '.bot.message_template' /workspace/config.yaml)"
MAX_CHARS="$(yq -r '.bot.max_chars // 1900' /workspace/config.yaml)"
```

`TEMPLATE` carries `{placeholder}` tokens that match canonical Job field
names (e.g. `{title}`, `{company}`, `{location}`, `{posted_date}`,
`{url}`, `{matched_keyword}`, `{site}`, `{salary}`, `{work_type}`,
`{employment_type}`, `{experience_level}`, `{job_id}`, `{posted_at}`,
`{requirements}`).

## Step 3 — Format per job

For each job in `results[*].sites[*].jobs`, substitute every
`{field_name}` placeholder in `TEMPLATE` with the job's value for that
field. If a referenced field is null/missing, drop the line containing
that placeholder rather than emitting a literal `null`. Anchors
(`title`, `company`, `url`) are always present.

**Handling `{posted_date}`**: Reformat ISO dates (`YYYY-MM-DD`) to `Weekday, DD Month YYYY` (e.g. `2026-05-26` → `Tuesday, 26 May 2026`). Leave non-ISO values unchanged.

**Handling `{requirements}`**: The raw value may contain mixed sections
(duties, qualifications, benefits). Extract only candidate-facing items —
things the candidate must have, know, or be. Common section headings to
keep: "What We're Looking For", "Requirements", "Qualifications", "We Need".
Strip sections describing job duties ("What You'll Do", "Responsibilities")
and benefits ("What You'll Gain", "Perks"). Format the extracted items as a
bullet list, one item per line, prefixed with `•`. If no clear qualification
section exists, use the full value as-is.

If the per-site result has `count: 0`, skip silently (don't post a
"no jobs found" message — too noisy).

If a final formatted message exceeds `MAX_CHARS`, truncate to fit and
append `…` to the truncated line.

## Step 4 — Post each job to Discord

Both the bot token and the channel ID come from the bot container's
environment:

- `DISCORD_BOT_TOKEN` — Discord application bot token (with
  `Send Messages` permission in the target channel)
- `DISCORD_CHANNEL_ID` — destination channel ID

Send each job as a **separate message** to that channel. One API call
per job. Loop through all jobs and post individually via `node` — read
the env vars inside the script, never inline the token:

```sh
export MSG=<formatted message for one job>
node -e "
const https = require('https');
const body = JSON.stringify({content: process.env.MSG});
const req = https.request({
  hostname: 'discord.com',
  path: '/api/v10/channels/' + process.env.DISCORD_CHANNEL_ID + '/messages',
  method: 'POST',
  headers: {
    'Authorization': 'Bot ' + process.env.DISCORD_BOT_TOKEN,
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(body)
  }
}, res => {
  let d=''; res.on('data',c=>d+=c);
  res.on('end',()=>{const r=JSON.parse(d); console.log(r.id ? 'sent: '+r.id : 'error: '+JSON.stringify(r));});
});
req.write(body); req.end();
"
```

## Step 5 — Summary footer (optional)

After all individual job messages, send one final summary line:

```
Scraped {total_jobs} jobs across {len(keywords)} keyword(s) and
{len(requested_sites)} site(s). Errors: {len(errors)}.
```

Skip this footer if `total_jobs == 0` (the run produced nothing useful).

## Step 6 — Record the Discord outcome in MongoDB

`scrape_jobs` already stored this run (raw + filtered results, per-site counts).
Your job here is only to add the Discord columns to that **same** document.

If `mongo_id` from Step 1 is null, skip this step (Mongo was unreachable; job
posting already happened and takes priority).

Otherwise call the `job-scraper` MCP tool `update_scrape_run` with:

```json
{
  "run_id": "<mongo_id from Step 1>",
  "patch": {
    "channel_id": "<value of DISCORD_CHANNEL_ID>",
    "discord_sent_status": "<'success' if no posts failed, else 'failed'>",
    "run_metadata.bot_post_status": {
      "total_posted": "<number of Discord messages sent successfully>",
      "failed": "<number that errored or got a non-2xx response>"
    }
  }
}
```

Notes:
- `discord_sent_status` is `"success"` when `failed == 0` (including when there
  were no jobs to post), else `"failed"`.
- Store `channel_id` only — **never** put `DISCORD_BOT_TOKEN` in the patch.
- The `"run_metadata.bot_post_status"` dot-notation key updates the nested field
  without overwriting the rest of `run_metadata`.
- If `update_scrape_run` returns `{ok: false}`, print one diagnostic line
  (`MongoDB update failed: <error>`) but do **not** retry or abort.

## Notes

- Do **not** call `update_config`. This prompt is read-only against the
  scraper's behavior — change config separately when needed.
- Deduplicate within a single run if the same `url` appears under
  multiple keywords (rare but possible). Post each unique URL once.
- The `bot.message_template` and `bot.max_chars` are loaded fresh on
  every run, so an edit + redeploy is enough — no prompt rewrite needed.
