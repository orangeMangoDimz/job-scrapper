#!/usr/bin/env bash
set -euo pipefail

# One-shot dev test of the scrape → Discord post flow using the dev config overlay.
# Merges config.yaml + config.dev.patch.yaml, starts mongo + scraper-mcp via the
# dev compose stack, then fires cron/run-scraper.sh directly inside a fresh bot
# container. Tears down the MCP stack on exit.
#
# Requires:
#   .env                - must contain DISCORD_WEBHOOK_URL,
#                         MONGO_ROOT_PASSWORD (sourced automatically by this script)
#   ~/.claude           - your local Claude Code session config dir
#   ~/.claude.json      - your local Claude Code config file
#   yq                  - https://github.com/mikefarah/yq
#
# Usage:
#   ./scripts/test_cron_dev.sh

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

COMPOSE_BASE="docker-compose.yml"
COMPOSE_ENV="docker-compose.dev.yml"
MERGED_CONFIG="/tmp/config.dev.yaml"

# --- guards ---
if ! command -v yq &>/dev/null; then
  echo "ERROR: yq not found — install it first: https://github.com/mikefarah/yq" >&2
  exit 1
fi

if [ ! -f "$REPO_ROOT/.env" ]; then
  echo "ERROR: .env not found — copy .env.example and set MONGO_ROOT_PASSWORD" >&2
  exit 1
fi

# Load .env into the current shell so bash guards and docker run -e can see them.
# Compose reads .env automatically; bash does not — this bridges that gap.
# set -a exports every variable assigned while active; set +a stops that.
# Variables already exported in the shell are not overridden.
set -a
# shellcheck source=/dev/null
source "$REPO_ROOT/.env"
set +a

CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CLAUDE_CONFIG_FILE="${CLAUDE_CONFIG_FILE:-$HOME/.claude.json}"

: "${DISCORD_WEBHOOK_URL:?set DISCORD_WEBHOOK_URL before running}"

if [ ! -d "$CLAUDE_CONFIG_DIR" ]; then
  echo "ERROR: Claude config dir not found at $CLAUDE_CONFIG_DIR" >&2
  echo "Run 'claude login' first, or set CLAUDE_CONFIG_DIR" >&2
  exit 1
fi
if [ ! -f "$CLAUDE_CONFIG_FILE" ]; then
  echo "ERROR: Claude config file not found at $CLAUDE_CONFIG_FILE" >&2
  exit 1
fi

# --- validate dev stack state ---
# Use `docker ps -a` (all statuses) so containers in Restarting/Exited state
# are still detected as present — the MCP readiness probe below handles health.
MCP_RUNNING=false
MONGO_RUNNING=false
docker ps -a --filter "name=job-scraper-mcp" -q | grep -q . && MCP_RUNNING=true || true
docker ps -a --filter "name=job-scraper-mongo" -q | grep -q . && MONGO_RUNNING=true || true

STACK_WAS_RUNNING=false
if [ "$MCP_RUNNING" = true ] && [ "$MONGO_RUNNING" = true ]; then
  echo "==> Dev stack already running (job-scraper-mcp + job-scraper-mongo). Reusing it."
  STACK_WAS_RUNNING=true
elif [ "$MCP_RUNNING" = true ] || [ "$MONGO_RUNNING" = true ]; then
  echo "ERROR: Dev stack is partially running — bring it fully down before retrying:" >&2
  echo "  docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile mcp down" >&2
  exit 1
fi

# --- merge dev config ---
echo "==> Merging config.yaml + config.dev.patch.yaml -> ${MERGED_CONFIG}..."
yq eval-all 'select(fileIndex == 0) * select(fileIndex == 1)' \
  "$REPO_ROOT/config.yaml" \
  "$REPO_ROOT/config.dev.patch.yaml" \
  > "$MERGED_CONFIG"

# --- start dev MCP stack (mongo + scraper-mcp) if not already up ---
if [ "$STACK_WAS_RUNNING" = false ]; then
  echo "==> Starting dev MCP stack (mongo + scraper-mcp)..."
  docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" --profile mcp up --build -d
fi

cleanup() {
  if [ "$STACK_WAS_RUNNING" = false ]; then
    echo "==> Tearing down dev MCP stack..."
    docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" --profile mcp down
  else
    echo "==> Dev stack was already running before test — leaving it up."
  fi
}
trap cleanup EXIT

# --- wait for MCP readiness ---
# Any HTTP response (including 400) means the server is up — only "000" means
# connection refused. The -f flag would wrongly treat 4xx as failure.
echo "==> Waiting for MCP to be ready..."
MCP_READY=false
for i in $(seq 1 20); do
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 -X POST \
      -H 'Accept: application/json, text/event-stream' \
      -H 'Content-Type: application/json' \
      -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
      http://localhost:8080/mcp)
  if [ "$HTTP_CODE" != "000" ] && [ -n "$HTTP_CODE" ]; then
    MCP_READY=true
    break
  fi
  if ! docker ps --filter "name=job-scraper-mcp" --filter "status=running" -q | grep -q .; then
    echo "ERROR: scraper-mcp container died. Logs:" >&2
    docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" logs scraper-mcp >&2
    exit 1
  fi
  sleep 1
done

if [ "$MCP_READY" = false ]; then
  echo "ERROR: MCP did not become ready after 20 seconds. Logs:" >&2
  docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" logs scraper-mcp >&2
  exit 1
fi
echo "==> MCP is up."

# --- fire cron/run-scraper.sh in the running bot container ---
echo "==> Running cron/run-scraper.sh in job-scraper-bot..."
docker exec job-scraper-bot /bin/sh /workspace/scraper-bot/cron/run-scraper.sh

echo "==> Done. Dev MCP stack will be torn down by trap."
