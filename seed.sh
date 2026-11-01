#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

_env() { grep -E "^${1}=" "${ENV_FILE}" 2>/dev/null | head -1 | cut -d= -f2-; }

MONGO_HOST="${MONGO_HOST:-127.0.0.1}"
MONGO_PORT="${MONGO_PORT:-27017}"
MONGO_USER="${MONGO_ROOT_USER:-$(_env MONGO_ROOT_USER)}"
MONGO_USER="${MONGO_USER:-admin}"
MONGO_PASS="${MONGO_ROOT_PASSWORD:-$(_env MONGO_ROOT_PASSWORD)}"

if [[ -z "${MONGO_PASS}" ]]; then
  echo "ERROR: MONGO_ROOT_PASSWORD not set and not found in .env" >&2
  exit 1
fi

export MONGO_URI="mongodb://${MONGO_USER}:${MONGO_PASS}@${MONGO_HOST}:${MONGO_PORT}/?authSource=admin"
# `|| true`: this key is optional, and a failed grep would stop the script under set -e
MONGO_DB_NAME="${MONGO_DB_NAME:-$(_env MONGO_DB_NAME || true)}"
export MONGO_DB_NAME="${MONGO_DB_NAME:-job_scraper}"

TARGET="${1:-all}"
PYTHON="${SCRAPER_PYTHON:-${SCRIPT_DIR}/.venv/bin/python}"

seed_wilayah() {
  NODE_PATH="$(npm root -g 2>/dev/null || true)" node "${SCRIPT_DIR}/seeds/wilayah.runner.js"
}

seed_job_settings() {
  if [[ ! -x "${PYTHON}" ]]; then
    echo "ERROR: ${PYTHON} not found. Create .venv or set SCRAPER_PYTHON" >&2
    exit 1
  fi
  (cd "${SCRIPT_DIR}" && "${PYTHON}" -m scraper.seed_settings)
}

echo "[seed] target: ${MONGO_HOST}:${MONGO_PORT} (user=${MONGO_USER}, seed=${TARGET})"

case "${TARGET}" in
  all)
    seed_wilayah
    seed_job_settings
    ;;
  wilayah) seed_wilayah ;;
  job-settings) seed_job_settings ;;
  *)
    echo "Usage: $0 [all|wilayah|job-settings]" >&2
    exit 1
    ;;
esac

echo "[seed] all done"
