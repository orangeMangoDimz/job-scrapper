#!/usr/bin/env bash
set -euo pipefail

# Start the prod environment (proxy enabled, uses config.yaml).
# Requires a SOCKS5 proxy running on host port 1080.
#
# Usage:
#   ./scripts/run_prod.sh           # both mcp + bot
#   ./scripts/run_prod.sh mcp       # MCP server only
#   ./scripts/run_prod.sh bot       # bot only
#   ./scripts/run_prod.sh ui        # MCP server + UI + Caddy (needs UI_* values in .env)

# --- config ---
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_BASE="docker-compose.yml"
COMPOSE_ENV="docker-compose.prod.yml"
PROXY_HOST="localhost"
PROXY_PORT="1080"
ARG="${1:-all}"

# --- guards ---
if ! curl -sf --socks5 "${PROXY_HOST}:${PROXY_PORT}" --max-time 3 https://ifconfig.me -o /dev/null; then
  echo "ERROR: SOCKS5 proxy not reachable at ${PROXY_HOST}:${PROXY_PORT} — start your proxy first." >&2
  exit 1
fi

# --- resolve profiles ---
case "$ARG" in
  mcp)  PROFILES="--profile mcp" ;;
  bot)  PROFILES="--profile bot" ;;
  ui)   PROFILES="--profile mcp --profile ui" ;;
  all)  PROFILES="--profile mcp --profile bot" ;;
  *)
    echo "Usage: $0 [mcp|bot|ui]" >&2
    exit 1
    ;;
esac

# --- shared network ---
# docker-compose.yml declares job-net as external, so compose will not create it.
docker network inspect job-net >/dev/null 2>&1 || docker network create job-net >/dev/null

# --- run ---
cd "$REPO_ROOT"

echo "==> Starting prod environment (proxy: socks5://${PROXY_HOST}:${PROXY_PORT}, services: ${ARG})..."
docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" $PROFILES up --build -d
