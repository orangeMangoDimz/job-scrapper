#!/bin/sh
LOG=/workspace/scraper-bot/cron/scraper.log
ENABLED="${BOT_SCHEDULE_ENABLED:-true}"

case "$ENABLED" in
  true)
    exec /bin/sh /workspace/scraper-bot/cron/run-scraper.sh
    ;;
  false)
    echo "[$(date)] BOT_SCHEDULE_ENABLED is false, skipping scheduled run." | tee -a "$LOG"
    ;;
  *)
    echo "[$(date)] ERROR: BOT_SCHEDULE_ENABLED must be true or false, got '$ENABLED'" | tee -a "$LOG" >&2
    exit 1
    ;;
esac
