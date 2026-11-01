# Deploy pipeline

GitHub Actions builds **two** Docker images, pushes both to GitHub
Container Registry, and SSHs into the VPS to (re)create both
containers via `docker run`.

Trigger: push to `main` (or manual via "Run workflow" in the Actions tab).

**Fully isolated**: nothing on the VPS host beyond docker itself. No
mounted files, no state directories, no manual config. Each deploy
starts both containers fresh from new images. Configuration baked into
images at build time; secrets injected via `docker run -e`.

## What ships

| Image | Container | Role |
|---|---|---|
| `ghcr.io/<owner>/<repo>:mcp-<sha>` | `scraper-mcp` | FastMCP HTTP server on port 8080 |
| `ghcr.io/<owner>/<repo>:bot-<sha>` | `scraper-bot` | supercronic + Claude Code CLI; fires the prompt on schedule and posts to Discord |

Both also tagged as `:mcp-latest` / `:bot-latest`.

## What the pipeline does

1. **build-mcp** — build `mcp-server` Dockerfile target → push
2. **build-bot** — build `bot` Dockerfile target → push (parallel with build-mcp)
3. **build-ui** — build `ui-server` Dockerfile target → push (parallel with build-mcp)
4. **deploy-mcp** — SSH, `docker pull` + replace `scraper-mcp` container
5. **deploy-bot** — SSH, `docker pull` + replace `scraper-bot` container with secrets injected
6. **deploy-ui** — SSH, `docker pull` + replace `scraper-ui` and start Caddy

deploy-bot runs after deploy-mcp so the MCP server is up before the bot
starts cron-firing. deploy-ui runs last, so two deploys never touch the
VPS at the same time.

## Required GitHub secrets

Repo → Settings → Secrets and variables → Actions → **Secrets** tab.

| Secret | Used by | Value |
|---|---|---|
| `SSH_HOST` | all deploy jobs | `43.157.226.237` |
| `SSH_USER` | all deploy jobs | `ubuntu` |
| `SSH_PRIVATE_KEY` | all deploy jobs | private key for VPS SSH |
| `DISCORD_BOT_TOKEN` | deploy-bot | Discord application bot token (with Send Messages perm in target channel) |
| `DISCORD_CHANNEL_ID` | deploy-bot | Discord channel ID where job posts go |
| `UI_PASSWORD_HASH` | deploy-ui | Argon2 hash of the UI password, see `.env.example` |
| `UI_SESSION_SECRET` | deploy-ui | Random string, at least 32 characters, see `.env.example` |

`GITHUB_TOKEN` is auto-provided — used to push to ghcr.io.

## Required GitHub variables

Same UI, but the **Variables** tab. Plain text (visible in logs and to
anyone with read access). Use these for non-secret config:

| Variable | Used by | Value |
|---|---|---|
| `CLAUDE_CONFIG_DIR` | deploy-bot | `/home/ubuntu/.claude` (host path mounted into bot for Claude session auth) |
| `CLAUDE_CONFIG_FILE` | deploy-bot | `/home/ubuntu/.claude.json` (host file mounted into bot) |
| `UI_DOMAIN` | deploy-ui | Public domain for the UI, with DNS pointing to the VPS |
| `MCP_BIND_HOST` | all deploy jobs | Optional. Docker gateway IP of the VPS, default `172.17.0.1` |
| `SCRAPER_PROXY_URL` | `deploy-mcp` | Required. Proxy URL for scrapes, such as `socks5://localhost:1080`. The deploy fails when it is missing or empty |

## Claude Code authentication

The bot uses **session-based auth** from your existing Claude Code login —
not an API key. The `deploy-bot` job mounts these from the VPS host:

| Host path | Container path |
|---|---|
| `/home/ubuntu/.claude` | `/home/node/.claude` |
| `/home/ubuntu/.claude.json` | `/home/node/.claude.json` |

These contain the auth session created when you ran `claude login` on
the VPS. The bot inherits that session — same Claude account, same
config, no API key required.

Both paths are pulled from GitHub repo variables `CLAUDE_CONFIG_DIR` and
`CLAUDE_CONFIG_FILE` (see "Required GitHub variables" above). Update
those values in repo settings if your `.claude` config lives elsewhere
on the VPS — no code change needed.

If those files don't exist on the VPS, the bot will start but `claude`
calls will fail. Run `claude login` once on the VPS as the `ubuntu`
user before the first deploy.

## Hardcoded values (workflow env block)

| Var               | Default       | Purpose                          |
|-------------------|---------------|----------------------------------|
| MCP `CONTAINER_NAME` | `scraper-mcp` | Name of the MCP container     |
| Bot `CONTAINER_NAME` | `scraper-bot` | Name of the bot container     |

Edit `.github/workflows/deploy.yml` if you want different container names.

## Networking

scraper-bot reaches scraper-mcp via `host.docker.internal:8080` — the
`--add-host=host.docker.internal:host-gateway` flag in the bot's
`docker run` exposes the VPS host as a resolvable name from inside the
bot container. The bot's baked-in `.mcp.json` points at this URL.

scraper-mcp listens on the Docker gateway address (`MCP_BIND_HOST`, default
`172.17.0.1`), so containers on the VPS can reach it through
`host.docker.internal:8080` and the public cannot. Do not set it to `127.0.0.1`,
which would cut off the bot.

scraper-ui has no published port. Caddy is its only public entry, on ports 80 and
443. Required before the first deploy: `UI_PASSWORD_HASH` and `UI_SESSION_SECRET`
secrets, a `UI_DOMAIN` variable, and a DNS record pointing to the VPS.

## ghcr.io image visibility

The first push creates each package as **private**. To let the VPS pull
without authentication:

1. GitHub profile → **Packages** → click each package
2. **Package settings** → **Change visibility** → **Public**

Alternatively, keep them private and run once on the VPS:

```bash
echo $PERSONAL_ACCESS_TOKEN | docker login ghcr.io -u <your-username> --password-stdin
```

with a token that has `read:packages` scope.

## Changing config

Job settings live in Mongo. The rest is baked in:

| Want to… | How |
|---|---|
| Change keywords, limits, filters, sites | Edit at `/config`. Applies from the next run, no deploy |
| Change the proxy | Update the `SCRAPER_PROXY_URL` GitHub variable → redeploy |
| Change cron schedule | Edit `bot.schedule` in `config.yaml` → push to `main` (bot Dockerfile reads it via `yq` at build time) |
| Change Discord message format | Edit `bot.message_template` in `config.yaml` → push to `main` (read fresh each run, no rebuild needed) |
| Change Discord per-message cap | Edit `bot.max_chars` in `config.yaml` → push to `main` |
| Change Discord channel | Update `DISCORD_CHANNEL_ID` GitHub secret → push to main (or manual deploy) |
| Change bot prompt | Edit `prompts/scrape-and-post.md` → push to `main` |
| Rotate Discord bot token | Update `DISCORD_BOT_TOKEN` secret → push to main |
| Rotate Claude session | Re-run `claude login` on the VPS as `ubuntu` user — bot picks it up on next start |

Note: `update_config` MCP tool writes go to Mongo and survive deploys. The
last 20 versions stay in history, see "Version history" in `runbook.md`.

## Manual rollback

To roll back to a previous SHA, trigger the workflow on that older
commit (Actions tab → "Run workflow" → choose ref).

Or directly on the VPS:

```bash
ssh ubuntu@<host>

# MCP rollback
docker pull ghcr.io/orangemangodimz/job-scrapper:mcp-<previous-sha>
docker stop scraper-mcp && docker rm scraper-mcp
docker run -d --name scraper-mcp --restart unless-stopped -p 8080:8080 \
  ghcr.io/orangemangodimz/job-scrapper:mcp-<previous-sha>

# Bot rollback (need to re-supply env vars + .claude mounts)
docker pull ghcr.io/orangemangodimz/job-scrapper:bot-<previous-sha>
docker stop scraper-bot && docker rm scraper-bot
docker run -d --name scraper-bot --restart unless-stopped \
  --add-host=host.docker.internal:host-gateway \
  -v /home/ubuntu/.claude:/home/node/.claude \
  -v /home/ubuntu/.claude.json:/home/node/.claude.json \
  -e DISCORD_BOT_TOKEN=... \
  -e DISCORD_CHANNEL_ID=... \
  ghcr.io/orangemangodimz/job-scrapper:bot-<previous-sha>
```

## Trigger flow

| Action | Result |
|--------|--------|
| Push commit to `main` | All 4 jobs run: build-mcp, build-bot, deploy-mcp, deploy-bot |
| PR merged into `main` | Same |
| Manual run | Actions tab → "Build & Deploy scraper" → Run workflow |
| Push to feature branch / `dev` | No deploy. Use PRs against `dev`, then merge `dev` → `main` for prod |

## Local sanity check

### Quick image build

Build either image locally before pushing to main:

```bash
docker build --target mcp-server -t job-scraper-mcp:local .
docker build --target bot -t job-scraper-bot:local .
```

If both boot, the same Dockerfile targets will build in CI.

### End-to-end test (skip cron, fire one-shot)

`scripts/test-locally.sh` builds both images, starts the MCP server,
and fires the bot's `run-scraper.sh` once — same code path supercronic
would trigger, but synchronous and immediate.

```bash
export DISCORD_BOT_TOKEN=<your bot token>
export DISCORD_CHANNEL_ID=<test channel id>
./scripts/test-locally.sh
```

The script:
1. Builds `mcp-server` and `bot` Dockerfile targets
2. Starts a local `scraper-mcp-test` container on port 8080
3. Waits for the MCP server to respond
4. Runs the bot container with your `~/.claude` config bind-mounted
   (for Claude session auth) and the secrets injected, executing
   `run-scraper.sh` once
5. Cleans up the MCP container on exit

If the bot's prompt completes successfully, you'll see Discord messages
appear in the test channel.

### Tweaks via env

```bash
CLAUDE_CONFIG_DIR=~/work-claude ./scripts/test-locally.sh    # different config dir
MCP_NAME=my-scraper-test ./scripts/test-locally.sh           # different test container name
```

## Seeding reference data

The `wilayah` collection stores Indonesian administrative area codes
(91 599 rows, Kepmendagri No 300.2.2-2138 Tahun 2025). It is **not**
seeded by the deploy pipeline — run this once on a fresh MongoDB or
after a data refresh.

### Prerequisites

- SSH tunnel to the VPS MongoDB (port 27017) active locally
- Node.js installed locally
- `mongodb` npm package: `npm install -g mongodb` (or local)

### Open tunnel

**DataGrip**: connect the data source — the SSH tunnel stays open while
DataGrip is connected. Note the local port it binds (visible in the
SSH/SSL tab of the data source settings).

**Manual**:
```bash
ssh -L 27017:localhost:27017 ubuntu@43.157.226.237 -N
```

### Run the seeder

```bash
MONGO_URI="mongodb://admin:<MONGO_ROOT_PASSWORD>@127.0.0.1:<LOCAL_PORT>/?authSource=admin" \
NODE_PATH=$(npm root -g) \
node seeds/wilayah.runner.js
```

- `MONGO_ROOT_PASSWORD` — value from your production `.env` / VPS secrets
- `LOCAL_PORT` — `27017` for manual tunnel; check DataGrip SSH/SSL tab if using DataGrip

The script drops the existing `wilayah` collection, inserts all batches,
creates a `nama` index, and verifies the exact row count. It exits
non-zero on mismatch.

### Seed job settings

Run this once on a fresh MongoDB, and before the first deploy that reads job settings. It only inserts when the document is missing.

```bash
MONGO_HOST=127.0.0.1 MONGO_PORT=<LOCAL_PORT> MONGO_ROOT_PASSWORD=<MONGO_ROOT_PASSWORD> ./seed.sh job-settings
```

Without this document, scrapes stop with a message that names this command.

## Bot's first run on a new schedule

The bot's crontab default is `0 1 * * *` (daily at 01:00). After the
first deploy, the next scheduled run is whenever cron's clock matches.
To trigger immediately:

```bash
ssh ubuntu@<host>
docker exec scraper-bot /bin/sh /workspace/scraper-bot/cron/run-scraper.sh
```

This runs the same script supercronic would, immediately, in the same
container with the same env.
