#!/bin/sh
# Cron job: run claude-code with the markdown prompt.
# Logs stream to STDOUT (supercronic -> `docker logs`, Factor XI). Set BOT_LOG_FILE
# to ALSO append to a file. Model precedence: CLAUDE_MODEL > config.yaml bot.model > default.
PROMPT=/workspace/scraper-bot/prompts/scrape-and-post.md
CONFIG=/workspace/config.yaml
DEFAULT_MODEL="claude-haiku-4-5-20251001"

MODEL="${CLAUDE_MODEL:-}"
if [ -z "$MODEL" ] && [ -f "$CONFIG" ]; then
  MODEL="$(yq -r '.bot.model // ""' "$CONFIG" 2>/dev/null || true)"
fi
[ -n "$MODEL" ] || MODEL="$DEFAULT_MODEL"

cd /workspace/scraper-bot
echo "[$(date)] starting multi-site scraper run (model=$MODEL)..."

run_claude() {
  # --dangerously-skip-permissions: unattended cron, no TTY to approve prompts.
  # --verbose --output-format stream-json: one JSON event per step (streams live).
  claude \
    --model "$MODEL" \
    --dangerously-skip-permissions \
    --verbose \
    --output-format stream-json \
    -p "$(cat "$PROMPT")" \
    2>&1
}

if [ -n "${BOT_LOG_FILE:-}" ]; then
  # capture claude's rc (not tee's) through a temp file — POSIX sh has no PIPESTATUS
  { run_claude; echo "$?" >/tmp/claude.rc; } | tee -a "$BOT_LOG_FILE"
  EXIT_CODE="$(cat /tmp/claude.rc)"; rm -f /tmp/claude.rc
else
  run_claude
  EXIT_CODE=$?
fi

if [ "$EXIT_CODE" -ne 0 ]; then
  echo "[$(date)] ERROR: claude exited with code $EXIT_CODE" >&2
fi
echo "[$(date)] run complete."
