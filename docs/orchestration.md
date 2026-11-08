# Orchestration: cron → Claude → Discord

Long-running container with supercronic fires `claude -p "<prompt>"` on a
schedule. The Claude session calls the `scrape_jobs` MCP tool, formats
the result, and posts each job to Discord using the bot token already
saved by the channel plugin during pairing. No webhooks involved.

This mirrors the legacy `job-scraper` container in
`/home/ubuntu/bots/personal-bots` on the VPS. Same shape, different
prompt and a different MCP backend.

## Architecture

```
┌──────────────────────────────────────┐         ┌──────────────────────┐
│  scraper-bot container               │         │   scraper-mcp        │
│  (long-running, Claude image)        │         │   long-running       │
│                                      │  MCP    │   HTTP :8080         │
│   supercronic ─→ run-scraper.sh      │ ──────► │   reads Mongo        │
│        │                             │         │   runs scrape        │
│        ▼                             │         │   returns aggregated │
│   claude -p "$(cat prompts/...)"     │ ◄────── │   JSON               │
│        │                             │         └──────────────────────┘
│        │  reads bot token from
│        │  /home/node/.claude/channels/discord/.env
│        │
│        ▼  POST /api/v10/channels/<id>/messages
│   Discord channel
└──────────────────────────────────────┘
```

Both containers share the same Docker network so `http://scraper-mcp:8080`
resolves from `scraper-bot`. Scraper-bot has the user's `.claude` dir
mounted, which is how it gets the Discord bot token saved by the channel
plugin during initial pairing.

## Files in this repo (templates)

| File | Purpose |
|---|---|
| `cron/entrypoint.sh` | downloads supercronic on first boot, exec's it |
| `cron/run-scraper.sh` | runs `claude --verbose --output-format stream-json -p "$(cat prompts/scrape-and-post.md)"` (streams step events live to the log) |
| `cron/run-scheduled-scraper.sh` | what each cron tick runs: calls `run-scraper.sh` when `BOT_SCHEDULE_ENABLED` is `true` (the default), skips the tick when `false`, fails on any other value |
| `cron/scraper-crontab` | the schedule (default: `0 1 * * *` — daily at 01:00) |
| `prompts/scrape-and-post.md` | the prompt Claude reads each tick — calls MCP tool, formats, posts |
| `claude/mcp.json.example` | project-level MCP registry template (rename to `.mcp.json` when copying to VPS) |
| `.env.example` | required env vars for VPS deployment |

These are templates, not active services in this repo's `docker-compose.yml`.
The repo only ships `scraper` (CLI) and `scraper-mcp` (MCP server).
The bot container lives in your personal-bots compose on the VPS.

## Deployment to the VPS personal-bots stack

1. **Copy this repo's templates** to `/home/ubuntu/bots/personal-bots/scraper-bot/`:
   ```
   /home/ubuntu/bots/personal-bots/scraper-bot/
   ├── cron/
   │   ├── entrypoint.sh
   │   ├── run-scraper.sh
   │   └── scraper-crontab
   ├── prompts/
   │   └── scrape-and-post.md
   └── .mcp.json                 (rename from this repo's claude/mcp.json.example)
   ```

2. **Run scraper-mcp** somewhere on the same Docker network. Options:
   - Build from this repo on the VPS and add a service to your personal-bots compose
   - Pull a prebuilt image from a registry
   - Run as a separate compose stack (then attach scraper-bot to that
     network with `external: true`)

3. **Add the scraper-bot service** to your personal-bots `docker-compose.yml`,
   mirroring your legacy `job-scraper` block:
   ```yaml
     scraper-bot:
       image: ${CLAUDE_IMAGE}
       container_name: scraper-bot
       restart: unless-stopped
       shm_size: ${SHM_SIZE}
       entrypoint: ["/bin/sh", "/workspace/scraper-bot/cron/entrypoint.sh"]
       environment:
         - DISCORD_CHANNEL_ID=${DISCORD_CHANNEL_ID}
       extra_hosts:
         - "host.docker.internal:host-gateway"
       volumes:
         - ${CLAUDE_CONFIG_DIR}:/home/node/.claude
         - ${CLAUDE_CONFIG_FILE}:/home/node/.claude.json
         - ${WORKSPACE_DIR}:/workspace
       healthcheck:
         test: ["CMD", "pgrep", "-f", "supercronic"]
         interval: ${HC_INTERVAL}
         timeout: ${HC_TIMEOUT}
         retries: ${HC_RETRIES}
         start_period: ${HC_START_PERIOD}
   ```

4. **Add scraper-bot's env to `/home/ubuntu/bots/personal-bots/.env`**:
   ```
   CLAUDE_IMAGE=claude-code
   CLAUDE_CONFIG_DIR=/home/ubuntu/.claude
   CLAUDE_CONFIG_FILE=/home/ubuntu/.claude.json
   WORKSPACE_DIR=/home/ubuntu/bots/personal-bots
   DISCORD_CHANNEL_ID=1330393101084266609
   SHM_SIZE=2gb
   HC_INTERVAL=30s
   HC_TIMEOUT=10s
   HC_RETRIES=3
   HC_START_PERIOD=60s
   ```

   And pass `DISCORD_CHANNEL_ID` into the bot container by adding it to
   the `environment:` block of the scraper-bot service (or by using
   compose's automatic env file expansion).

5. **Bring it up**:
   ```bash
   cd /home/ubuntu/bots/personal-bots
   docker compose up -d scraper-mcp scraper-bot
   docker compose logs -f scraper-bot
   ```

## Bot config block

All bot-tunable settings live under the `bot:` block in `config.yaml`:

```yaml
bot:
  schedule: "0 1 * * *"          # supercronic cron expression
  max_chars: 1900                # per-message Discord cap (Discord limit is 2000)
  message_template: |            # per-job message template; supports {field}
    ## {title}
    {company} | {location} | {posted_date}
    [link]({url})

    Matched: {matched_keyword} on {site}
```

| Setting | When it's read | Effect |
|---|---|---|
| `bot.schedule` | Bot image build time (yq → crontab) | Cron cadence supercronic uses |
| `bot.max_chars` | Each prompt run (Claude reads via yq) | Truncates messages above this length |
| `bot.message_template` | Each prompt run | Format applied to every job |

Schedule examples (standard cron + supercronic shorthand):

```yaml
schedule: "0 10 * * *"       # daily 10:00 (default; Asia/Jakarta timezone)
schedule: "0 */6 * * *"      # every 6h
schedule: "*/30 * * * *"     # every 30 min
schedule: "@every 1h"        # supercronic shorthand
```

The schedule is evaluated against the bot container's clock. The deploy
workflow injects `TZ=Asia/Jakarta` by default — override by setting a
`TZ` GitHub repo variable (e.g. `Asia/Singapore`, `Etc/UTC`).

Template placeholders match canonical Job field names — use any of:
`title`, `company`, `url`, `location`, `salary`, `posted_date`,
`posted_at`, `work_type`, `employment_type`, `experience_level`,
`job_id`, `matched_keyword`, `site`, `requirements`. Lines whose
placeholder resolves to null get dropped.

Edit → commit → push to main → deploy rebuilds the bot image (for
schedule) and the next run picks up template/max_chars changes
without further work.

## Discord posting

The prompt instructs Claude to:

1. Read the bot token from `/home/node/.claude/channels/discord/.env`
   (saved there by `/discord:configure` during pairing)
2. POST each job as a separate message to the channel ID supplied by the
   `DISCORD_CHANNEL_ID` environment variable (set in the bot container's
   env via your `personal-bots/.env`)
3. Use Node's `https` module via `node -e` to keep token in env vars,
   never inlined in shell

To change the Discord channel, set `DISCORD_CHANNEL_ID` in your
`personal-bots/.env` and restart the bot container.

To change the bot, re-pair via `/discord:configure` and restart the bot
container so the new token in `/home/node/.claude/channels/discord/.env`
is picked up.

## How `scraper-mcp` is reached

The scraper-bot container has `claude/.mcp.json` accessible at the
project root inside the workspace. When `claude -p` runs from
`/workspace/scraper-bot/`, it picks up `.mcp.json` and registers the
`job-scraper` MCP server.

The default URL is `http://host.docker.internal:8080/mcp` — the
scraper-mcp container is deployed standalone (see `docs/deploy.md`)
and listens on the VPS's host port `8080`. The `extra_hosts:
"host.docker.internal:host-gateway"` line in the bot's compose service
maps that name to the Docker bridge gateway so the bot can reach the
host's published port from inside the container.

If you'd rather register globally (so all your Claude containers see it),
add the entry to `${CLAUDE_CONFIG_FILE}` (the `.claude.json` you mount).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Container restarts on healthcheck failure | supercronic process not running | Check `cron/scraper.log` for crontab parse errors |
| Cron fires but Claude exits with `mcp not found` | `.mcp.json` not in scope | Verify `claude -p` is run with cwd = workspace dir; or add to global `.claude.json` |
| Claude logs `connection refused: host.docker.internal:8080` | scraper-mcp not running, or `extra_hosts` missing from bot compose | `docker ps` to confirm scraper-mcp is up on host port 8080; verify `extra_hosts: ["host.docker.internal:host-gateway"]` is in the bot service |
| Discord post fails with 401 | Bot token not saved at `/home/node/.claude/channels/discord/.env` | Re-run `/discord:configure <token>` on the user's host Claude session |
| Discord post fails with 403 | Bot lacks send-messages perm in channel | Re-invite bot with the right OAuth scopes |
| Cron never fires | Bad crontab syntax | `docker exec scraper-bot /workspace/scraper-bot/cron/supercronic -test /workspace/scraper-bot/cron/scraper-crontab` |

## Cost considerations

Each cron tick = one Claude API call. With Sonnet pricing and a
multi-site scrape result, expect ~$0.05–0.20 per tick. At daily cadence
that's ~$1.50–6/month. Tighten the schedule or prompt to control cost.
