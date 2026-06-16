#!/bin/sh
# Bot entrypoint: build the crontab at CONTAINER START (Factor IX disposability +
# runtime config) instead of baking it at image-build time. Precedence:
#   BOT_SCHEDULE env  >  .bot.schedule in /workspace/config.yaml  >  default.
# POSIX sh (bot /bin/sh is the node:20-slim shell). yq is installed in the image.
set -e

CONFIG=/workspace/config.yaml
CRONTAB=/workspace/scraper-bot/cron/scraper-crontab
DEFAULT_SCHEDULE="0 11 * * *"

SCHEDULE="${BOT_SCHEDULE:-}"
if [ -z "$SCHEDULE" ] && [ -f "$CONFIG" ]; then
  SCHEDULE="$(yq -r '.bot.schedule // ""' "$CONFIG" 2>/dev/null || true)"
fi
[ -n "$SCHEDULE" ] || SCHEDULE="$DEFAULT_SCHEDULE"

echo "[entrypoint] cron schedule: $SCHEDULE"
printf '%s /bin/sh /workspace/scraper-bot/cron/run-scraper.sh\n' "$SCHEDULE" > "$CRONTAB"

exec /usr/local/bin/supercronic "$CRONTAB"
