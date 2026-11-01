#!/bin/sh
# Cron entrypoint: runs claude-code with a markdown prompt, logs all output.
# POSIX sh (not bash): supercronic/docker invoke this as `/bin/sh run-scraper.sh`,
# and the bot image's /bin/sh is dash — so no bashisms (e.g. ${PIPESTATUS}).
LOG=/workspace/scraper-bot/cron/scraper.log
PROMPT=/workspace/scraper-bot/prompts/scrape-and-post.md

echo "[$(date)] starting multi-site scraper run..." | tee -a "$LOG"
cd /workspace/scraper-bot
# --dangerously-skip-permissions: needed for unattended cron — no TTY to approve prompts
# --disallowedTools: the run reads untrusted job text, so it must not change or restore
#   scraper config even if that text tries to make it
# --verbose --output-format stream-json: emit one JSON event per step (tool calls,
#   assistant messages, result) so the run's internals stream live to the log.
#   Default text mode buffers and prints only the final result at the very end;
#   --verbose alone does not stream. --verbose is required for stream-json.
# Stream claude output to console + log, but capture *claude's* exit (not tee's).
# POSIX sh has no ${PIPESTATUS}, so route the real rc through a file.
{
  claude \
    --model claude-haiku-4-5-20251001 \
    --dangerously-skip-permissions \
    --disallowedTools "mcp__job-scraper__update_config,mcp__job-scraper__restore_config" \
    --verbose \
    --output-format stream-json \
    -p "$(cat "$PROMPT")" \
    2>&1
  echo "$?" >"$LOG.rc"
} | tee -a "$LOG"
EXIT_CODE="$(cat "$LOG.rc")"; rm -f "$LOG.rc"

if [ "$EXIT_CODE" -ne 0 ]; then
  echo "[$(date)] ERROR: claude exited with code $EXIT_CODE" | tee -a "$LOG" >&2
fi

echo "[$(date)] run complete." | tee -a "$LOG"
