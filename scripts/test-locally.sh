#!/usr/bin/env bash
set -euo pipefail

# One-shot local test of the scrape → Discord post flow.
# Starts the mcp-profile stack (mongo + scraper-mcp) via docker compose,
# then fires `cron/run-scraper.sh` directly inside a one-shot bot container.
# Requires:
#
#   DISCORD_BOT_TOKEN   - bot token with Send Messages perm in target channel
#   DISCORD_CHANNEL_ID  - channel ID to post into
#   ~/.claude           - your local Claude Code session config dir
#   ~/.claude.json      - your local Claude Code config file
#
# Usage:
#   export DISCORD_BOT_TOKEN=...
#   export DISCORD_CHANNEL_ID=...
#   ./scripts/test-locally.sh

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_BASE="docker-compose.yml"
COMPOSE_ENV="docker-compose.dev.yml"
cd "$REPO_ROOT"

if [ -f "$REPO_ROOT/.env" ]; then
  set -a && source "$REPO_ROOT/.env" && set +a
fi

: "${DISCORD_BOT_TOKEN:?set DISCORD_BOT_TOKEN before running}"
: "${DISCORD_CHANNEL_ID:?set DISCORD_CHANNEL_ID before running}"

if [ ! -d "$HOME/.claude" ]; then
  echo "Claude config dir not found at $HOME/.claude" >&2
  echo "Run 'claude login' first" >&2
  exit 1
fi
if [ ! -f "$HOME/.claude.json" ]; then
  echo "Claude config file not found at $HOME/.claude.json" >&2
  exit 1
fi

cleanup() {
  echo "==> Stopping MCP stack..."
  docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" --profile mcp down
}
trap cleanup EXIT

# --- shared network ---
# docker-compose.yml declares job-net as external, so compose will not create it.
docker network inspect job-net >/dev/null 2>&1 || docker network create job-net >/dev/null

echo "==> Building images..."
docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" build scraper-mcp bot

echo "==> Starting MCP stack (mongo + scraper-mcp)..."
docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" --profile mcp up -d

echo "==> Waiting for MCP to be ready..."
for i in $(seq 1 20); do
  if curl -sf -o /dev/null -X POST \
      -H 'Accept: application/json, text/event-stream' \
      -H 'Content-Type: application/json' \
      -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
      http://localhost:8080/mcp; then
    break
  fi
  if docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" ps scraper-mcp 2>/dev/null | grep -qiE "exited|dead"; then
    echo "scraper-mcp died. Logs:" >&2
    docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" logs scraper-mcp >&2
    exit 1
  fi
  sleep 1
done
echo "==> MCP is up."

echo "==> Firing bot one-shot (skipping supercronic, running run-scraper.sh directly)..."
docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" run --rm \
  --entrypoint /bin/bash \
  bot /workspace/scraper-bot/cron/run-scraper.sh

echo "==> Done. MCP stack will be stopped by trap."
