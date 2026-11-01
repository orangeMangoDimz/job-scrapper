#!/usr/bin/env bash
set -euo pipefail

# Start the dev environment. Job settings come from this machine's Mongo.
# First run: ./seed.sh job-settings
#
# Usage:
#   ./scripts/run_dev.sh           # mcp + bot + ui
#   ./scripts/run_dev.sh mcp       # MCP server only
#   ./scripts/run_dev.sh bot       # bot only
#   ./scripts/run_dev.sh ui        # MCP server + UI at http://127.0.0.1:8090

# --- config ---
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_BASE="docker-compose.yml"
COMPOSE_ENV="docker-compose.dev.yml"
ARG="${1:-all}"

# --- ui file access ---
# scraper-ui writes host-owned output/ui-runs, so it runs as the host user in dev.
export UI_UID="$(id -u)" UI_GID="$(id -g)"

# --- resolve profiles ---
case "$ARG" in
  mcp)  PROFILES="--profile mcp" ;;
  bot)  PROFILES="--profile bot" ;;
  ui)   PROFILES="--profile mcp --profile ui" ;;
  all)  PROFILES="--profile mcp --profile bot --profile ui" ;;
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

echo "==> Starting dev environment (services: ${ARG})..."
docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" $PROFILES up --build -d
