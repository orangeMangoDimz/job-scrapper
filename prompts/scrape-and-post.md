# Multi-site job scrape

Execute all steps below now, in order. Do not ask for confirmation.

## Step 1 — Run the scraper

Call the `job-scraper` MCP tool `scrape_jobs` with no arguments. It will run
every enabled site for every configured keyword, applying the recency and
content filters from the bound `config.yaml`, and return aggregated results.

The response shape is:

```json
{
  "keywords": ["software engineer", "data analyst"],
  "requested_sites": ["jobstreet", "glints", "linkedin", "indeed"],
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

## Step 2 — Pull the message template

```sh
TEMPLATE="$(cat /workspace/scraper-bot/prompts/response_template.md)"
```

`TEMPLATE` carries `{placeholder}` tokens that match canonical Job field
names (e.g. `{title}`, `{company}`, `{location}`, `{posted_date}`,
`{url}`, `{matched_keyword}`, `{site}`, `{salary}`, `{work_type}`,
`{employment_type}`, `{experience_level}`, `{job_id}`, `{posted_at}`,
`{requirements}`).

## Step 3 — Format per job

For each job in `results[*].sites[*].jobs`, substitute every
`{field_name}` placeholder in `TEMPLATE` with the job's value for that field.

**Null handling.** Drop the *placeholder*, not the whole line. Remove the token
along with any separator left dangling beside it (` | `, a trailing `:`), then
drop the line only if nothing but its label survives. This matters for lines
carrying two fields: `{company} | {location}` must still render the company when
the location is null. Anchors (`title`, `company`, `url`) are always present.

A **section header whose entire body was dropped must drop with it** — if a job
has no requirements, the `**Kualifikasi**` heading goes too, rather than sitting
above nothing.

**Handling `{posted_date}`**: values arrive in mixed shapes — bare dates
(`2026-07-18`) and full ISO-8601 timestamps (`2026-07-16T11:06:12.929Z`,
`2026-07-17T05:00:00+00:00`). Normalize **any** ISO-8601 value to
`Weekday, DD Month YYYY`, with no time of day:

- If it carries a timezone, convert to **UTC+7 (WIB)** before formatting, so the
  date matches the reader's local day.
  e.g. `2026-07-17T22:30:00Z` → `Friday, 18 July 2026`.
- If it is a bare `YYYY-MM-DD`, treat it as already WIB and do not shift it.
- Anything that will not parse passes through unchanged.

**Handling `{requirements}`**: the value is a slice of the raw job description,
already windowed server-side by `requirements_max_chars`. The window is anchored
on the qualifications heading, so the text may begin *and* end mid-document and
is marked with a leading/trailing `…` when it does — that is expected, do not
flag it and do not repeat the `…` in your output.

Emit the block as **its own heading line, then at most 3 bullets**, each at most
80 characters, one per line prefixed with `•`, truncating an over-long item with
`…`. The template supplies no heading — you choose it:

- **Preferred — a real qualifications section.** Extract candidate-facing items:
  things the candidate must have, know, or be. Keep sections like "What We're
  Looking For", "Requirements", "Qualifications", "We Need", "Kualifikasi".
  Strip duties ("What You'll Do", "Responsibilities") and benefits ("Perks").
  Head the block `**Kualifikasi**`.
- **Fallback — no clean qualifications section.** The server-side anchor matches
  the word "requirements" anywhere, so it sometimes lands mid-sentence inside
  the duties text. Do **not** drop the block in that case. Fall back to the
  first 3 substantive lines of the value, skipping company boilerplate ("About
  <Company>", marketing copy). Head the block `**Ringkasan**` so duties are not
  mislabelled as qualifications.
- Drop the block entirely — heading included, per the null rule above — only
  when the value is null or contains nothing but boilerplate.

If the per-site result has `count: 0`, skip silently (don't post a
"no jobs found" message — too noisy).

## Step 4 — Assemble the digest file

Everything the run produced goes into **one markdown file**, not into chat
messages. Write it to:

```sh
DIGEST_PATH="/tmp/jobs-$(date +%F).md"
```

`TZ=Asia/Jakarta` is set in the container, so `date +%F` is already the WIB date.
Use the `Write` tool for the file — job text contains backticks and `$`, which a
shell heredoc would mangle unless quoted.

Structure, top to bottom:

1. A bold title line and an italic summary line — **plain text, not headings**,
   so they don't compete with the keyword headers below:

   ```md
   **Job digest — Friday, 20 July 2026**

   _Scraped 29 jobs across 5 keyword(s) and 4 site(s). Errors: 1._
   ```

2. One `# <keyword>` section per keyword that produced jobs (level-1; job titles
   from the template are level-2, so the hierarchy holds).

3. Under each keyword, the formatted job blocks from Step 3.

Separate **every** block with a blank line, then `---`, then a blank line — after
the title/summary header, between jobs, and before each new `# <keyword>`
heading. Two reasons:

- The blank line before `---` matters now that this is a real file: `---`
  directly under text is a setext heading, not a horizontal rule.
- `send-digest.js` splits oversized digests on exactly that separator, so a
  missing one welds two jobs into an unsplittable block.

Skip keywords and sites with `count: 0` — no "no jobs found" filler.

There is no per-message character budget any more. Do **not** truncate, drop or
summarize jobs to make things fit; the sender handles size (see Step 5).

## Step 5 — Send the digest to Discord

One command. Do not write your own HTTP code — `cron/send-digest.js` owns the
upload, the 10 MiB split, rate-limit retries and the fallback path:

```sh
DIGEST_PATH="/tmp/jobs-$(date +%F).md" \
DIGEST_SUMMARY="<summary line, prefixed by the error diagnostic if any>" \
  node /workspace/scraper-bot/cron/send-digest.js
```

(Spell the path out again — each shell call is a fresh process, so a variable set
in Step 4 is gone by now.)

- `DISCORD_WEBHOOK_URL` is already in the container env; never pass it as an
  argument and never inline it.
- `DIGEST_SUMMARY` is the visible message body — it carries the same footer that
  used to be its own message:
  `Scraped {total_jobs} jobs across {len(keywords)} keyword(s) and
  {len(requested_sites)} site(s). Errors: {len(errors)}.`
  If Step 1 reported `exit_code != 0` or a non-empty `errors`, put the one-line
  diagnostic on the line above it.
- If `total_jobs == 0`, skip Steps 4 and 5 entirely — no file, no post.

The script prints one machine-readable line as its last output:

```
RESULT {"mode":"attachment","messages_sent":1,"parts":1,"bytes":48213,"failed":0}
```

`mode` is `attachment` (normal), `inline` (every upload failed, jobs went out as
plain messages), or `mixed`. Read these numbers from that line in Step 6 — do
not recompute them.

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
    "discord_sent_status": "<'success' if RESULT.failed == 0, else 'failed'>",
    "run_metadata.bot_post_status": {
      "total_posted": "<RESULT.messages_sent>",
      "total_jobs_posted": "<number of jobs you wrote into the digest>",
      "failed": "<RESULT.failed>",
      "delivery_mode": "<RESULT.mode>"
    }
  }
}
```

Notes:
- `total_posted` is a *message* count — normally `1`, more when the digest was
  split or the fallback fired. `total_jobs_posted` is the job count that
  reconciles against the run total, and is the only field you supply yourself.
- `delivery_mode` records whether the run degraded to inline posting, which is
  otherwise invisible after the fact.
- **Never** put `DISCORD_WEBHOOK_URL` (it embeds a secret token) in the patch.
- The `"run_metadata.bot_post_status"` dot-notation key updates the nested field
  without overwriting the rest of `run_metadata`.
- If `update_scrape_run` returns `{ok: false}`, print one diagnostic line
  (`MongoDB update failed: <error>`) but do **not** retry or abort.

## Notes

- Do **not** call `update_config`. This prompt is read-only against the
  scraper's behavior — change config separately when needed.
- `scrape_jobs` already applies cross-run deduplication server-side: it only
  returns jobs not seen in previous runs, and never the same posting twice
  within a run. Just post everything it returns — no extra dedup needed.
- The message template (`prompts/response_template.md`) is read fresh on every
  run, so editing the template file is enough — no prompt rewrite needed.
- `MAX_CHARS` no longer shapes normal output. It only caps the inline messages
  `send-digest.js` falls back to when uploads fail, and the script reads it
  itself.
