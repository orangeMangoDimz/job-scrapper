#!/usr/bin/env bash
set -euo pipefail

# One-shot local test of the scrape → Discord post flow.
# Starts the mcp-profile stack (mongo + scraper-mcp) via docker compose,
# then fires `cron/run-scraper.sh` directly inside a one-shot bot container.
# Requires:
#
#   DISCORD_WEBHOOK_URL - Discord webhook URL to post into
#   ~/.claude           - your local Claude Code session config dir
#   ~/.claude.json      - your local Claude Code config file
#
# Usage:
#   export DISCORD_WEBHOOK_URL=...
#   ./scripts/test-locally.sh

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_BASE="docker-compose.yml"
COMPOSE_ENV="docker-compose.dev.yml"
MERGED_CONFIG="/tmp/config.dev.yaml"
cd "$REPO_ROOT"

if [ -f "$REPO_ROOT/.env" ]; then
  set -a && source "$REPO_ROOT/.env" && set +a
fi

: "${DISCORD_WEBHOOK_URL:?set DISCORD_WEBHOOK_URL before running}"

if ! command -v yq &>/dev/null; then
  echo "ERROR: yq not found — install it first: https://github.com/mikefarah/yq" >&2
  exit 1
fi

if [ ! -d "$HOME/.claude" ]; then
  echo "Claude config dir not found at $HOME/.claude" >&2
  echo "Run 'claude login' first" >&2
  exit 1
fi
if [ ! -f "$HOME/.claude.json" ]; then
  echo "Claude config file not found at $HOME/.claude.json" >&2
  exit 1
fi

echo "==> Merging config.yaml + config.dev.patch.yaml -> ${MERGED_CONFIG}..."
yq eval-all 'select(fileIndex == 0) * select(fileIndex == 1)' \
  "$REPO_ROOT/config.yaml" \
  "$REPO_ROOT/config.dev.patch.yaml" \
  > "$MERGED_CONFIG"

cleanup() {
  echo "==> Stopping MCP stack..."
  docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" --profile mcp down
}
trap cleanup EXIT

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
