# What is this

Personal job scraper for Indonesian job boards (JobStreet, Glints, LinkedIn,
Indeed). Flow: a Playwright/Python scraper is exposed as an **MCP HTTP server**
(`scraper-mcp`, port 8080); a **Discord cron bot** (claude-code + supercronic)
runs on a schedule, calls the MCP `scrape_jobs` tool, formats results, posts
them to a Discord channel as a single markdown digest attachment, and records
the run in **MongoDB**.

Four Dockerfile stages: `scraper-cli` (`python -m scraper`),
`mcp-server` (`python -m mcp_server.server`), `bot`, plus `mongo` (MongoDB 7).
Config-driven by `config.yaml` (keywords, sites, filters, bot schedule).

# How to run locally

Prereqs: Docker + Docker Compose, a Python venv.

Launch the interactive Docker manager TUI:

```bash
python scripts/manage.py
```

**TUI deps are separate from the runtime (Docker image) deps.** Install them first:

```bash
pip install -r scripts/requirements.txt   # textual + pyyaml — NOT the root requirements.txt
```

The root `requirements.txt` is baked into the Docker images and is not needed on the host.

The TUI is a single Textual screen with:

- **Env bar** — `dev` / `prod` buttons (default `dev`, from `scripts/environments.yaml`)
- **Summary panel** — shows merged keywords, enabled sites, proxy status, mongo db/collection, masked `.env` secrets
- **Command preview panel** — shows the exact command that will run when you press a button
- **Action rows** — one row per scope (`all`, `bot`, `mcp`, `mongo`); columns: Start / Stop (labelled **Down** on the `all` row) / Status / Logs
- **Tests row** — dev smoke tests: Scrape / Mongo / Cron / Discord
- Keys: `q`/`ctrl+c` quit, `c` cancel running command, `r` refresh status, `x`/`ctrl+l` clear log

Equivalent raw command to start the MCP stack in dev (the TUI does this for you):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile mcp up --build -d
```

Before first run, copy the `.example` files (see section below).

# Test with local Claude and local MCP

This is for a **`claude` CLI you run on your host machine** (your laptop terminal,
in the repo dir) to talk to the dockerized MCP server — handy for ad-hoc testing
without going through the bot. This is a _different_ client from the dockerized
bot, which ships its own baked `claude-code` and uses `host.docker.internal`
(see [MCP on Docker](#mcp-on-docker)).

It works because `scraper-mcp` publishes its port to the host
(`docker-compose.yml`: `ports: "8080:8080"`), so `localhost:8080` on your host
forwards into the container.

Copy the example to a project-root `.mcp.json` (where host `claude` picks it up):

```bash
cp claude/mcp.json.example .mcp.json
```

Then edit `.mcp.json` and change the URL from `host.docker.internal` to `localhost`:

```json
{
  "mcpServers": {
    "job-scraper": {
      "type": "http",
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

Start the MCP server first (TUI → `mcp` → Start, or the raw command in
[How to run locally](#how-to-run-locally)), then verify:

```bash
curl http://localhost:8080/health
```

# MCP on Docker

The bot container uses `http://host.docker.internal:8080/mcp` instead of
`localhost` — `localhost` inside a container refers to the container itself, not
the host. The value in `claude/mcp.json.example` already ships with the Docker
URL and is baked into the bot image as `/workspace/scraper-bot/.mcp.json`
(Dockerfile `bot` stage).

Compose wiring that makes this work:

- `bot` service has `extra_hosts: ["host.docker.internal:host-gateway"]` (Linux)
- In prod, `scraper-mcp` uses `network_mode: host`, so it listens on the host's
  `:8080` that `host.docker.internal` resolves to

# Ports used here

| Service       | Port  | Bind                                      | Notes                                                    |
| ------------- | ----- | ----------------------------------------- | -------------------------------------------------------- |
| `scraper-mcp` | 8080  | `0.0.0.0:8080` (dev); host network (prod) | MCP HTTP; `/health` and `/mcp` endpoints                 |
| `mongo`       | 27017 | `127.0.0.1:27017`                         | profiles `mcp`, `mongo`; data in `mongo-data` volume     |
| `bot`         | —     | none                                      | outbound only (Discord API, `host.docker.internal:8080`) |

# Copy the .example files

| Example                         | Copy to                 | Purpose                                                          |
| ------------------------------- | ----------------------- | ---------------------------------------------------------------- |
| `.env.example`                  | `.env`                  | local compose env vars: Discord tokens, Mongo creds, `PROXY_URL` |
| `config.dev.patch.yaml.example` | `config.dev.patch.yaml` | dev config overrides (merged over `config.yaml`)                 |
| `scripts/ssh-tunnel.sh.example` | `scripts/ssh-tunnel.sh` | reverse SOCKS proxy helper — gitignored, contains real host/user |
| `claude/mcp.json.example`       | `.mcp.json`             | MCP client config for Claude (update URL for host vs Docker)     |

`.env` is for local Docker Compose only. Production injects all env vars through
GitHub Actions secrets/variables — it never reads this file.

**MongoDB connection URL:** the app reads `MONGO_URI` (`mcp_server/mongo.py`). You
don't set it directly — Docker Compose derives it from `MONGO_ROOT_USER` +
`MONGO_ROOT_PASSWORD`:

- dev / bridge network (`docker-compose.yml`): `mongodb://<user>:<password>@mongo:27017`
- prod / host network (`docker-compose.prod.yml`): `mongodb://<user>:<password>@localhost:27017`

Outside Docker the code default is `mongodb://localhost:27017`.

# Seed reference data

Run after MongoDB is up:

```bash
./seed.sh                                          # local (reads .env)
MONGO_HOST=127.0.0.1 MONGO_PORT=27018 ./seed.sh   # prod via SSH tunnel
```

Seeds are idempotent — drop + recreate each run.

**`wilayah`** — 91 599 Indonesian administrative region codes (Kepmendagri No 300.2.2-2138
Tahun 2025). Source: [cahyadsn/wilayah](https://github.com/cahyadsn/wilayah/tree/6ff9b8a2764cd4fbeb8c15fe0cba2d5a4eb26107)
([wilayah.sql](https://raw.githubusercontent.com/cahyadsn/wilayah/6ff9b8a2764cd4fbeb8c15fe0cba2d5a4eb26107/db/wilayah.sql)).
Runner: `seeds/wilayah.runner.js` (Node.js, requires `mongodb` package).

# SSH tunnel (reverse SOCKS proxy)

`scripts/ssh-tunnel.sh` opens a **reverse dynamic SOCKS5** tunnel (`ssh -R`) so
the remote scraper routes its outbound HTTP traffic through **this machine's**
residential IP, dodging datacenter-IP blocks that jobstreet/glints/linkedin apply
to cloud VPS addresses.

`config.yaml` has `proxy: socks5://localhost:1080`. In prod, `scraper-mcp` runs
`network_mode: host`, so `localhost:1080` on the remote server is the tunnel
endpoint provided by this script.

Setup:

```bash
cp scripts/ssh-tunnel.sh.example scripts/ssh-tunnel.sh
# Edit the file: set SSH_HOST and SSH_USER (or export them as env vars)
```

Commands:

```bash
./scripts/ssh-tunnel.sh up           # open the reverse SOCKS proxy
./scripts/ssh-tunnel.sh down         # close it
./scripts/ssh-tunnel.sh status       # proxy + mongo tunnel liveness + docker ps
./scripts/ssh-tunnel.sh test         # verify remote traffic exits via this machine's IP
./scripts/ssh-tunnel.sh mongo-up     # forward local :27018 → remote MongoDB
./scripts/ssh-tunnel.sh mongo-down   # close the mongo forward tunnel
./scripts/ssh-tunnel.sh mongo-status # show mongo tunnel liveness
./scripts/ssh-tunnel.sh mongo-test   # verify port reachable + mongosh ping
./scripts/ssh-tunnel.sh mongo-reset  # reset remote mongo root password (see below)
```

The `test` command confirms the proxied egress IP differs from the server's
direct egress IP. If they match, the tunnel is not working.

## Connecting to prod MongoDB from local machine

Prod MongoDB binds to `127.0.0.1:27017` on the server — not exposed publicly.
Use `mongo-up` to open a forward tunnel, then connect normally:

```bash
./scripts/ssh-tunnel.sh mongo-up
mongosh "mongodb://admin:<MONGO_ROOT_PASSWORD>@127.0.0.1:27018"
```

Any client connecting from outside the server (DataGrip, DBeaver, Compass, Python scripts)
must go through the tunnel the same way — run `mongo-up` first, then connect using
`mongodb://<user>:<password>@127.0.0.1:27018`. Verify with `mongo-test`:

```bash
./scripts/ssh-tunnel.sh mongo-up
./scripts/ssh-tunnel.sh mongo-test
```

Default local port is `27018` (not `27017`) to avoid conflict with a running dev
mongo container. Override if needed:

```bash
MONGO_PORT=27019 ./scripts/ssh-tunnel.sh mongo-up
```

### "Authentication failed" against prod mongo

If `mongo-test` reports auth failure (and `job-scraper-mcp` shows `unhealthy`)
even though `MONGO_ROOT_PASSWORD` looks correct, the volume was **first**
initialized with different creds. `MONGO_INITDB_ROOT_USERNAME` / `_PASSWORD`
only apply on the **first** mongod start against an **empty** `mongo-data`
volume — once data exists, mongod stores creds in the volume and ignores those
env vars forever. So changing the GitHub secret and redeploying has **no
effect** on the password.

Fix in place (keeps data) — reset the stored password to `MONGO_ROOT_PASSWORD`:

```bash
./scripts/ssh-tunnel.sh mongo-reset
```

This SSHes in, stops the authed mongo, boots a throwaway no-auth mongo on the
same volume, sets the `admin` password, then restarts the real container (a
`trap` restarts it even if a step fails). Re-run `mongo-test` to confirm.

Alternative (clean slate, **loses scrape history**): remove the container +
volume so the next start re-initializes from current env:

```bash
docker rm -f job-scraper-mongo && docker volume rm job-scrapper_mongo-data
# then redeploy, or `docker compose ... --profile mcp up -d`
```

# Deployment process

`.github/workflows/deploy.yml` — triggers on push to `main` or manual
`workflow_dispatch`.

**Build jobs** (`build-mcp` + `build-bot`, run in parallel):

- Build and push each Docker image to `ghcr.io`
- Two tags per image: rolling (`mcp-latest` / `bot-latest`) and immutable per-commit (`mcp-<sha>` / `bot-<sha>`)
- Uses GitHub Actions layer cache to speed up rebuilds

**Deploy jobs** (sequential after their respective build):

1. `deploy-mcp` (needs `build-mcp`): copies `docker-compose.yml` + `docker-compose.prod.yml` to the server via SCP, then SSHs in and runs `docker compose --profile mcp pull && up -d --no-build`, pinned to the immutable sha tag
2. `deploy-bot` (needs `build-bot` + `deploy-mcp`): same flow for `--profile bot`, injects Discord tokens, Claude config paths, and `TZ`

# Config: config.yaml + the dev patch

`config.yaml` is the single source of truth, committed to the repo and baked
into Docker images at build time. Key fields:

| Field                   | Purpose                                                   |
| ----------------------- | --------------------------------------------------------- |
| `keywords`              | Job titles to search                                      |
| `limit` / `concurrency` | Global result cap and parallel fetches                    |
| `proxy`                 | SOCKS5/HTTP proxy URL; absent or `~` = direct connection  |
| `max_age_hours`         | Drop jobs older than this                                 |
| `filter.location`       | Keep only jobs matching these locations                   |
| `bot.schedule`          | Cron expression for the Discord bot (e.g. `"0 11 * * *"`) |
| `bot.message_template`  | Discord message format with `{field}` placeholders        |
| `bot.max_chars`         | Truncate messages to this length                          |
| `sites.*`               | Per-site `enabled`, `limit`, `url_template`, `fields`     |

**Do you need a dev version?** Yes (recommended). Create `config.dev.patch.yaml`
(copy from `config.dev.patch.yaml.example`) to override only what you need for
local testing — reduced limits, fewer sites, no proxy. No need to fork the whole
file.

**How the override works:** on a dev **Start**, the TUI runs:

```bash
yq eval-all 'select(fileIndex == 0) * select(fileIndex == 1)' \
  config.yaml config.dev.patch.yaml > /tmp/config.dev.yaml
```

The `yq` `*` operator deep-merges maps (nested dicts) and replaces scalars/lists
with the patch value. An explicit `null` (`~`) in the patch **overrides** the
base — so `proxy: ~` disables the proxy in dev (the scraper only activates a
proxy when the value is a non-empty string). The dev compose overlay then
bind-mounts `/tmp/config.dev.yaml` into the `scraper-mcp` container
(`docker-compose.dev.yml`).

In **prod**, `config_merge` is `null` in `scripts/environments.yaml`, so no
merge runs — the image-baked `config.yaml` is used directly.

> **Note on `bot.schedule`:** the crontab is generated from `config.yaml` at
> **image build time** (Dockerfile `bot` stage). Changing `bot.schedule` requires
> a rebuild and redeploy — editing `config.yaml` on a running container has no
> effect.

# How the filter works

`filter:` in `config.yaml` runs **after** scraping — not at the HTTP/URL level.
URL templates carry no location params. All search-page results are fetched and
parsed first, then filtered in Python.

Pipeline in `run_one` (`scraper/runner.py`):

1. Fetch search page (full HTTP request)
2. Parse all jobs from HTML
3. Drop jobs older than `max_age_hours`
4. **`apply_filter`** — drop jobs not matching `filter:` criteria
5. Fetch detail pages — only for jobs that survived step 4
6. Write output JSON

`apply_filter` (`scraper/sites/_filter.py`) does case-insensitive substring
matching per field. `location: [jakarta, tangerang]` keeps a job if
`job["location"].lower()` contains any of those strings.

Edge case: if a job's filtered field is `None` (site didn't return it), the
job passes through — it is not dropped.

# Cron job

In the bot image, `supercronic` is the entrypoint, running
`cron/scraper-crontab`. This file is generated at build time from `config.yaml`
`bot.schedule` (currently `0 11 * * *` — 11:00 AM daily). Each tick executes
`cron/run-scraper.sh`, which runs:

```bash
claude --dangerously-skip-permissions --verbose --output-format stream-json \
  -p "$(cat prompts/scrape-and-post.md)"
```

`--verbose --output-format stream-json` makes claude emit one JSON event per
step (tool calls, messages, result) so the run streams live to the log; default
text mode prints only the final result at the very end.

Output is logged to `/workspace/scraper-bot/cron/scraper.log`. `cron/entrypoint.sh`
just `exec`s supercronic.

**Who triggers it in prod:** supercronic inside the deployed `bot` container,
automatically on the baked schedule.

**In dev**, the bot is overridden to `sleep infinity` (`docker-compose.dev.yml`),
so it idles and does not run cron. To fire a run manually:

```bash
# Via TUI: tests row → Cron

# Or directly:
docker exec job-scraper-bot /bin/sh /workspace/scraper-bot/cron/run-scraper.sh
```

# Query MongoDB data

Connect to the Mongo shell:

```bash
docker exec -it job-scraper-mongo mongosh -u admin -p <MONGO_ROOT_PASSWORD> --authenticationDatabase admin
```

Then query the scrape history:

```js
use job_scraper

// all runs
db.scrape_runs.find({})

// latest first
db.scrape_runs.find({}).sort({ _id: -1 })

// count
db.scrape_runs.countDocuments()

// latest single run
db.scrape_runs.findOne({}, {}, { sort: { _id: -1 } })
```

# Clear / reset MongoDB data

⚠️ **Irreversible.** In MongoDB, columns (fields) live on the documents, not in a
fixed schema — deleting the documents removes the old fields with them. After a
wipe, only the columns the current code writes reappear on the next run.

Connect to the Mongo shell (same `docker exec … mongosh` as
[Query MongoDB data](#query-mongodb-data)), then:

```js
use job_scraper

// empty the collection — keeps it and its indexes (recommended)
db.scrape_runs.deleteMany({})

// or drop the collection (removes documents + indexes)
db.scrape_runs.drop()

// or drop the whole database
db.dropDatabase()
```

For **prod**, open the SSH tunnel first (see
[Connecting to prod MongoDB from local machine](#connecting-to-prod-mongodb-from-local-machine)),
then run the same commands.

# Check logs

Stream container logs:

```bash
docker logs -f job-scraper-mcp       # MCP server
docker logs -f job-scraper-bot       # Discord cron bot
docker logs -f job-scraper-mongo     # MongoDB
```

Via TUI: select a scope row → **Logs** (runs `docker compose … logs -f --tail=200 <services>`).

Read the cron run log inside the bot container:

```bash
docker exec job-scraper-bot cat /workspace/scraper-bot/cron/scraper.log
```

# How to debug the bot

The `bot` service (`docker-compose.yml`) mounts your host `~/.claude` +
`~/.claude.json` (or override via `CLAUDE_CONFIG_DIR`/`CLAUDE_CONFIG_FILE`),
needs `DISCORD_BOT_TOKEN` + `DISCORD_CHANNEL_ID` from `.env`, and reaches the
MCP server at `host.docker.internal:8080`.

In dev the bot idles (`sleep infinity`), so you can exec in freely.

**Start the bot container** (TUI → dev → `bot` → Start, or):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile bot up --build -d
```

**Check which MCP target is active** — the baked `.mcp.json` inside the container
uses `host.docker.internal:8080`. If you want to point the bot at a local
(non-Docker) MCP server, you need `localhost:8080` — these are different hosts.

**Interactive Claude session inside the bot:**

```bash
docker exec -it job-scraper-bot sh -c "cd /workspace/scraper-bot && claude"
```

Then run `/mcp` to list available servers and tools. The MCP server exposes:
`scrape_jobs`, `insert_scrape_run`, `get_latest_scrape_run`, `get_scrape_status`,
`list_sites`, `get_config`, `update_config`, `get_scrape_response_structure`,
`test_proxy_connection` — plus the `/health` HTTP endpoint.

**Quick smoke tests** (TUI tests row, no full cron run needed):

| Button      | What it tests                                                                               |
| ----------- | ------------------------------------------------------------------------------------------- |
| **Scrape**  | Runs `python -m scraper` in `scraper-mcp` — scrape only, no Mongo write, no Discord post    |
| **Mongo**   | Inserts + reads + drops a throwaway document in `scraper-mcp` via the real Mongo connection |
| **Discord** | Posts a throwaway digest via `cron/send-digest.js` from the bot container — the real send path |
| **Cron**    | Fires the full cron job once (`run-scraper.sh`) — real scrape + real Discord posts          |

# The scraping prompt (prompts/scrape-and-post.md)

This markdown file is what cron feeds to Claude on every run. It drives the full
scrape-and-post pipeline:

1. **Scrape** — call MCP `scrape_jobs` with no arguments; runs every enabled site
   for every configured keyword using `config.yaml` filters and returns aggregated
   results grouped by keyword → site → jobs
2. **Read the message template** — `prompts/response_template.md`, read fresh
   every run
3. **Format each job** — substitute `{field}` placeholders in the template; drop
   lines where the field is null; reformat ISO dates; distil `{requirements}` down
   to candidate-facing bullet points only
4. **Assemble the digest** — every formatted job goes into one markdown file
   (`/tmp/jobs-YYYY-MM-DD.md`), keywords as `#` sections
5. **Post to Discord** — a single webhook POST via `cron/send-digest.js`: the
   digest rides as a `.md` attachment, the message body carries only the summary
   line and any error diagnostic. The script splits the file if it exceeds the
   10 MiB upload cap, honours 429 `retry_after`, and falls back to inline
   `MAX_CHARS` messages if uploads keep failing. The webhook URL comes from the
   container env, never inlined
6. **Record run** — call MCP `insert_scrape_run` with metadata, per-site counts,
   raw results, and post status; job posting always takes priority over history
   recording

# GitHub Actions variables & secrets

Set these in your repository's **Settings → Secrets and variables**.

**Secrets** (encrypted, never logged):

| Secret                | Required by | Purpose                                |
| --------------------- | ----------- | -------------------------------------- |
| `SSH_HOST`            | deploy jobs | Server IP or hostname                  |
| `SSH_USER`            | deploy jobs | SSH login user                         |
| `SSH_PRIVATE_KEY`     | deploy jobs | Private key for SSH authentication     |
| `MONGO_ROOT_PASSWORD` | deploy-mcp  | MongoDB root password                  |
| `DISCORD_BOT_TOKEN`   | deploy-bot  | Discord bot application token          |
| `DISCORD_CHANNEL_ID`  | deploy-bot  | Target channel ID for job posts        |
| `GITHUB_TOKEN`        | build jobs  | Auto-provided; used to push to ghcr.io |

**Variables** (plain text, shown in logs):

| Variable                | Default        | Purpose                                             |
| ----------------------- | -------------- | --------------------------------------------------- |
| `MONGO_ROOT_USER`       | `admin`        | MongoDB root username                               |
| `MONGO_DB_NAME`         | `job_scraper`  | Database name                                       |
| `MONGO_COLLECTION_NAME` | `scrape_runs`  | Scrape history collection                           |
| `CLAUDE_CONFIG_DIR`     | —              | Host path to `.claude` directory (mounted into bot) |
| `CLAUDE_CONFIG_FILE`    | —              | Host path to `.claude.json` (mounted into bot)      |
| `TZ`                    | `Asia/Jakarta` | Timezone for the bot container                      |
