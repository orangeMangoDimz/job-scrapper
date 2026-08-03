#!/bin/sh
# Cron entrypoint: runs claude-code with a markdown prompt, logs all output.
# POSIX sh (not bash): supercronic/docker invoke this as `/bin/sh run-scraper.sh`,
# and the bot image's /bin/sh is dash — so no bashisms (e.g. ${PIPESTATUS}).
LOG=/workspace/scraper-bot/cron/scraper.log
PROMPT=/workspace/scraper-bot/prompts/scrape-and-post.md
MCP_CONFIG=/workspace/scraper-bot/.mcp.json

echo "[$(date)] starting multi-site scraper run..." | tee -a "$LOG"
cd /workspace/scraper-bot
# --mcp-config: load the job-scraper MCP server explicitly. The image also bakes
#   this file in as a project-scoped .mcp.json, but project-scoped servers need a
#   trust approval recorded per project path in CLAUDE_CONFIG_FILE — and that file
#   is seeded from a `claude login` on another machine, so the approval for
#   /workspace/scraper-bot is not in it. Passing the config explicitly sidesteps
#   the trust flow; without it the MCP tools can go missing and the run fails at
#   Step 1 with nothing posted.
# --strict-mcp-config: use ONLY the server above, so nothing inherited from the
#   PV-backed config can shadow or interfere with it.
# --dangerously-skip-permissions: needed for unattended cron — no TTY to approve
#   prompts. Covers tool permission checks, not MCP project trust.
# --verbose --output-format stream-json: emit one JSON event per step (tool calls,
#   assistant messages, result) so the run's internals stream live to the log.
#   Default text mode buffers and prints only the final result at the very end;
#   --verbose alone does not stream. --verbose is required for stream-json.
# Stream claude output to console + log, but capture *claude's* exit (not tee's).
# POSIX sh has no ${PIPESTATUS}, so route the real rc through a file.
{
  claude \
    --model claude-sonnet-5 \
    --mcp-config "$MCP_CONFIG" \
    --strict-mcp-config \
    --dangerously-skip-permissions \
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
