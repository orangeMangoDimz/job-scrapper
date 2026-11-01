#!/usr/bin/env bash
set -euo pipefail

# Start the dev environment (no proxy, config merged from config.yaml + config.dev.patch.yaml).
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
MERGED_CONFIG="/tmp/config.dev.yaml"
# Any locally available image with rmdir; mongo:7 is already pulled by the stack.
HELPER_IMAGE="mongo:7"
RECREATE_FLAG=""
ARG="${1:-all}"

# --- guards ---
if ! command -v yq &>/dev/null; then
  echo "ERROR: yq not found — install it first: https://github.com/mikefarah/yq" >&2
  exit 1
fi

# --- heal stale merged config ---
# /tmp is wiped on reboot. A container with a restart policy then starts before
# this script re-creates the file, so Docker creates the missing bind-mount
# source as a root-owned directory, which blocks the redirect below.
if [ -d "$MERGED_CONFIG" ]; then
  echo "==> ${MERGED_CONFIG} is a directory (stale Docker bind mount) — removing..."
  rmdir "$MERGED_CONFIG" 2>/dev/null ||
    docker run --rm --entrypoint rmdir \
      -v "$(dirname "$MERGED_CONFIG"):/host" "$HELPER_IMAGE" \
      "/host/$(basename "$MERGED_CONFIG")"
  RECREATE_FLAG="--force-recreate"
fi

# --- merge config ---
echo "==> Merging config.yaml + config.dev.patch.yaml -> ${MERGED_CONFIG}..."
yq eval-all 'select(fileIndex == 0) * select(fileIndex == 1)' \
  "$REPO_ROOT/config.yaml" \
  "$REPO_ROOT/config.dev.patch.yaml" \
  > "$MERGED_CONFIG"

# --- ui file access ---
# scraper-ui edits host-owned config files, so it runs as the host user in dev.
export UI_UID="$(id -u)" UI_GID="$(id -g)"
mkdir -p "$REPO_ROOT/config-backups"

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

# --- run ---
cd "$REPO_ROOT"

echo "==> Starting dev environment (no proxy, services: ${ARG})..."
docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_ENV" $PROFILES up --build -d $RECREATE_FLAG
