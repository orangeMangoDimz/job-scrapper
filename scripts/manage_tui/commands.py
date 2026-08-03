"""Build the exact command sequence for an (environment, scope, action).

This module is the single source of truth behind the "preview == exec"
guarantee: the UI renders `Command.preview()` for each step, and the runner
executes the very same `Command.argv`. They cannot drift because both derive
from the objects returned here.

A "sequence" is an ordered list of Commands run with stop-on-first-failure.
Most actions are a single command; dev `start` is two (yq merge, then up).
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from .model import CONTAINER_NAMES, Environment

ACTIONS = ("start", "stop", "status", "logs")
ALL = "all"
LOG_TAIL = "200"

# Dev smoke tests: each is one `docker exec` against an already-running
# container (started via the profile Start buttons). The keys are the button
# ids and the preview/run wiring in app.py iterates this tuple.
TESTS = ("scrape", "mongo", "cron", "discord")

_MCP_CONTAINER = CONTAINER_NAMES["scraper-mcp"]
_BOT_CONTAINER = CONTAINER_NAMES["bot"]

# Reuses the real Mongo connection/auth (mcp_server.mongo, MONGO_URI from the
# container env) but writes to an isolated throwaway collection so the real
# scrape_runs history — which the bot's get_latest_run() reads — stays clean.
_MONGO_PING_SCRIPT = """\
from mcp_server.mongo import get_collection
import datetime
coll = get_collection().database["_tui_healthcheck"]
doc_id = coll.insert_one(
    {"ping": "manage.py", "at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
).inserted_id
print("inserted", doc_id)
print("read-back", coll.find_one({"_id": doc_id}))
coll.drop()
print("dropped _tui_healthcheck -- mongo OK")
"""

# Writes a throwaway digest and posts it with cron/send-digest.js — the same
# script the cron prompt calls, so this test can't drift from the real send path
# the way an inlined copy of it did.
_DISCORD_TEST_MESSAGE = "✅ manage.py TUI discord test — webhook reachable"

_DISCORD_SEND_SH = f"""\
set -e
printf '%s\\n' '**manage.py TUI test digest**' '' '## Test job' 'Test Co | Jakarta' \
  > /tmp/tui-discord-test.md
DIGEST_PATH=/tmp/tui-discord-test.md \
DIGEST_SUMMARY='{_DISCORD_TEST_MESSAGE}' \
  node /workspace/scraper-bot/cron/send-digest.js
"""


@dataclass(frozen=True)
class Command:
    """One process invocation.

    stdout_path mirrors a shell `> file` redirect (needed for the yq merge,
    whose output is captured to a file). The runner opens that file for the
    child's stdout; the preview renders the ` > file` suffix so what the user
    sees matches what runs.
    """

    argv: list[str]
    stdout_path: str | None = None

    def preview(self) -> str:
        line = shlex.join(self.argv)
        if self.stdout_path:
            line += f" > {self.stdout_path}"
        return line


def build_sequence(
    env: Environment, scope: str, action: str, profile_map: dict[str, list[str]]
) -> list[Command]:
    base = _base(env)
    profiles = sorted(profile_map.keys())

    if action == "start":
        sequence: list[Command] = []
        merge = merge_command(env)
        if merge is not None:
            sequence.append(merge)
        sequence.append(
            Command(
                base
                + ["--progress", "plain"]
                + _profile_flags(scope, profiles)
                # --quiet-pull: layer-pull progress is carriage-return spam with
                # no newlines; silencing it keeps the log clean (and avoids
                # multi-MB no-newline "lines"). --progress plain handles build.
                + ["up", "--build", "--quiet-pull", "-d"]
            )
        )
        return sequence

    if action == "stop":
        # Every service here is profile-gated, and Compose v2 `down` only
        # targets services in the ACTIVE profile set — a bare `down` selects
        # nothing and leaves the stack running. So activate all profiles for the
        # whole-stack teardown, mirroring `status`. Per-profile teardown names
        # that profile's services explicitly with `stop`.
        if scope == ALL:
            return [Command(base + _profile_flags(ALL, profiles) + ["down"])]
        return [Command(base + ["stop", *profile_map.get(scope, [])])]

    if action == "status":
        # -a so stopped (exited-but-present) containers still show.
        # `all` enumerates every profile so profile-gated services are visible;
        # a specific scope names its services explicitly (verified visible to
        # `ps` without the --profile flag), so each row's status differs.
        if scope == ALL:
            return [Command(base + _profile_flags(ALL, profiles) + ["ps", "-a"])]
        return [Command(base + ["ps", "-a", *profile_map.get(scope, [])])]

    if action == "logs":
        services = [] if scope == ALL else profile_map.get(scope, [])
        return [Command(base + ["logs", "-f", f"--tail={LOG_TAIL}", *services])]

    raise ValueError(f"unknown action: {action!r}")


def merge_command(env: Environment) -> Command | None:
    """The yq merge, mirroring scripts/run_dev.sh. None when env has no merge."""
    merge = env.config_merge
    if merge is None:
        return None
    return Command(
        argv=[
            merge.tool,
            "eval-all",
            "select(fileIndex == 0) * select(fileIndex == 1)",
            merge.base,
            merge.patch,
        ],
        stdout_path=merge.output,
    )


def _base(env: Environment) -> list[str]:
    cmd = ["docker", "compose"]
    for compose_file in env.compose_files:
        cmd += ["-f", compose_file]
    return cmd


def _profile_flags(scope: str, profiles: list[str]) -> list[str]:
    targets = profiles if scope == ALL else [scope]
    flags: list[str] = []
    for profile in targets:
        flags += ["--profile", profile]
    return flags


def build_test(test: str) -> list[Command]:
    """One docker-exec Command per dev smoke test.

    Mirrors build_sequence: the UI previews Command.preview() and the runner
    executes Command.argv, so preview == exec holds here too. Each test runs
    against an already-running container — it does not start or tear down a
    stack. scrape/mongo need scraper-mcp up; cron/discord need bot up.

    The runner uses create_subprocess_exec (argv, no shell), so the multi-line
    python -c / node -e bodies pass as a single argv element with no escaping.
    """
    if test == "scrape":
        # python -m scraper is isolated: it scrapes only (no Mongo write, no
        # Discord post) using whatever config is loaded in the container.
        return [Command(["docker", "exec", _MCP_CONTAINER, "python", "-m", "scraper"])]
    if test == "mongo":
        return [Command(["docker", "exec", _MCP_CONTAINER, "python", "-c", _MONGO_PING_SCRIPT])]
    if test == "cron":
        # Same one-shot as scripts/test_cron_dev.sh: fires the full cron job
        # (claude scrape + real Discord posts) once inside the bot container.
        return [
            Command(
                [
                    "docker",
                    "exec",
                    _BOT_CONTAINER,
                    "/bin/sh",
                    "/workspace/scraper-bot/cron/run-scraper.sh",
                ]
            )
        ]
    if test == "discord":
        # DISCORD_WEBHOOK_URL already lives in the bot container env; the digest
        # file and summary are built inside the container by the snippet.
        return [
            Command(
                [
                    "docker",
                    "exec",
                    _BOT_CONTAINER,
                    "/bin/sh",
                    "-c",
                    _DISCORD_SEND_SH,
                ]
            )
        ]
    raise ValueError(f"unknown test: {test!r}")


def build_scrape_site(site: str) -> list[Command]:
    """Scrape one platform: docker exec job-scraper-mcp python -m scraper <site>."""
    return [Command(["docker", "exec", _MCP_CONTAINER, "python", "-m", "scraper", site])]
