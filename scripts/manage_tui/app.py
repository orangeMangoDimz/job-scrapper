"""Textual application: environment switcher, per-profile action rows,
command preview, and a streaming output log.

Focus an action button to preview the exact command(s); press it to run.
The preview is produced by commands.build_sequence and the same objects are
handed to the runner, so the preview is always what executes.
"""

from __future__ import annotations

import asyncio
import os
import subprocess

from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import Button, Footer, Header, RichLog, Static

from . import compose as compose_mod
from .commands import ACTIONS, ALL, TESTS, build_scrape_site, build_sequence, build_test
from .config_view import load_config_summary, masked_env
from .model import Manifest
from .runner import SequenceRunner

_SUMMARY_ENV_KEYS = (
    "MONGO_ROOT_USER",
    "MONGO_ROOT_PASSWORD",
    "DISCORD_WEBHOOK_URL",
)
_PREVIEW_HINT = "(focus an action — Tab/arrows — to preview its command)"

# Test button labels. Keys must match commands.TESTS; ids are f"test-{key}".
# scrape/mongo run against scraper-mcp; cron/discord run against bot.
_TEST_LABELS = {
    "scrape": "Scrape",
    "mongo": "Mongo",
    "cron": "Cron",
    "discord": "Discord",
}


def _row_under_pointer(event: events.MouseEvent) -> int | None:
    """Buffer index of the entry under the pointer, or None.

    The index rides in the cell's Rich style meta (the app writes each entry as a
    meta-tagged Text). Reading it off the live event is wrap-proof: every strip of
    one entry — including wrapped continuation rows — carries the same meta row, so
    we get the entry regardless of which visual row the pointer is on, no
    coordinate math. Returns None on a border/scrollbar/empty cell (no style) or a
    cell with no "row" meta, which all callers treat as "not on content".
    """
    style = event.style
    if style is None:
        return None
    return (style.meta or {}).get("row")


class ClickCopyLog(RichLog):
    """RichLog whose lines can be click-dragged to copy an inclusive range.

    Textual has no in-app text selection for RichLog (issue #5333), so this widget
    tracks a press-drag-release gesture at whole-line granularity and reports the
    selected row range to the app via RangeSelected; the app owns the buffer, the
    highlight, and the clipboard copy (this widget can't see them). A press with no
    movement is just a 1-line range — i.e. the old single-click-copies-one-line
    behaviour, with no separate code path.

    Why a self.capture_mouse() on press: once captured, every subsequent MouseMove
    and the MouseUp are routed here even if the pointer leaves the widget (drags
    that wander past the log border still extend/terminate cleanly). _anchor holds
    the press row; it is also the live "are we dragging?" flag (None == idle).

    Known gap: if the terminal/OS swallows the MouseUp mid-drag (focus loss,
    window occluded), the mouse stays captured app-wide — Textual gives no
    mid-capture unmount/blur hook here to auto-release. Self-recovers on the next
    press: on_mouse_down re-captures and the following up calls release_mouse().
    """

    class RangeSelected(Message):
        # Inclusive [lo, hi] buffer-index range. final=False is a live drag update
        # (highlight only); final=True is the release (highlight + copy).
        def __init__(self, lo: int, hi: int, final: bool) -> None:
            self.lo = lo
            self.hi = hi
            self.final = final
            super().__init__()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Row where the current drag started, or None when no drag is in flight.
        self._anchor: int | None = None

    def on_mouse_down(self, event: events.MouseDown) -> None:
        # Begin a gesture only when the press lands on real content. A press on the
        # border/scrollbar/empty area below the last line has no row meta, so we
        # leave _anchor None and never capture the mouse (the gesture is a no-op).
        row = _row_under_pointer(event)
        if row is None:
            return
        self._anchor = row
        # Route all later moves/up here even if the pointer leaves the widget.
        self.capture_mouse()
        # A bare press is already a valid 1-line range; report it live so the
        # single entry highlights immediately (and so a press-release with no move
        # still produces a (row, row) range to copy).
        self.post_message(self.RangeSelected(row, row, final=False))

    def on_mouse_move(self, event: events.MouseMove) -> None:
        # Only meaningful mid-drag. Outside a drag (_anchor None) every hover move
        # would otherwise spam range messages, so bail early.
        if self._anchor is None:
            return
        row = _row_under_pointer(event)
        if row is None:
            # Pointer slid onto the border/empty area mid-drag: hold the current
            # range rather than collapsing it, so a wandering cursor doesn't
            # shrink the selection. (No message posted → app keeps last range.)
            return
        self.post_message(
            self.RangeSelected(min(self._anchor, row), max(self._anchor, row), final=False)
        )

    def on_mouse_up(self, event: events.MouseUp) -> None:
        # Ignore stray ups with no active gesture (e.g. press began off content).
        if self._anchor is None:
            return
        self.release_mouse()
        # If the release lands off content, end the range at the anchor rather than
        # discarding the gesture — the user still pressed on a valid line.
        row = _row_under_pointer(event)
        if row is None:
            row = self._anchor
        # final=True triggers the copy in the app handler. Posted even when the
        # range is unchanged since the last move, so single-click (down→up, no
        # move) and drag-end (last move == release row) both copy.
        self.post_message(
            self.RangeSelected(min(self._anchor, row), max(self._anchor, row), final=True)
        )
        self._anchor = None


class ManagerApp(App):
    CSS = """
    Screen { layout: vertical; }

    /* Buttons default to height 3 in Textual; flattened to a single row so the
       control panels stay compact and never starve #log of vertical space.
       Default-height buttons were the bug: on a normal-height terminal the
       panels above consumed every row and the log collapsed / scrolled off. */
    Button { height: 1; min-width: 9; margin: 0 1 0 0; border: none; }
    Button:focus { text-style: reverse; }

    #envbar { height: 1; padding: 0 1; }

    /* summary + preview side by side, capped and internally scrollable so a
       long summary can never push the log off-screen on small terminals. */
    #top { height: auto; max-height: 11; }
    #summary { width: 1fr; height: auto; max-height: 11; overflow-y: auto;
               border: round $accent; padding: 0 1; margin: 0 1 0 0; }
    #preview { width: 1fr; height: auto; max-height: 11; overflow-y: auto;
               border: round $secondary; padding: 0 1; }

    #profiles { height: auto; max-height: 8; overflow-y: auto;
                border: round $primary; padding: 0 1; }
    .scope-row { height: 1; }
    .scope-label { width: 18; height: 1; content-align: left middle; }

    /* tests + scrape side by side to save one vertical row. */
    #bottom { height: auto; }
    #tests { height: auto; width: 1fr; border: round $warning; padding: 0 1; }
    #scrape { height: auto; width: 1fr; border: round $success; padding: 0 1; }

    /* The log takes the remaining space but is guaranteed a usable minimum so
       command output is always visible. */
    #log { height: 1fr; min-height: 5; border: round $panel; }
    """

    BINDINGS = [
        ("q", "quit_clean", "Quit"),
        ("ctrl+c", "quit_clean", "Quit"),
        ("c", "cancel", "Cancel run"),
        ("r", "refresh_status", "Status (all)"),
        ("x", "clear_log", "Clear output"),
        ("ctrl+l", "clear_log", "Clear output"),
        ("f", "toggle_log", "Log fullscreen"),
        ("ctrl+y", "copy_log", "Copy log"),
    ]

    def __init__(self, manifest: Manifest) -> None:
        super().__init__()
        self.manifest = manifest
        self.env_name = manifest.default_environment
        self.runner = SequenceRunner()
        self.profile_map = compose_mod.parse_profiles(self.env.compose_files)
        self._log_buffer: list[str] = []
        # Inclusive (lo, hi) buffer-index range of the click-drag selection
        # (persistent high-contrast highlight), or None when nothing is selected.
        # A single click is a (n, n) range. Cleared on clear-log.
        self._selected_range: tuple[int, int] | None = None

    @property
    def env(self):
        return self.manifest.environments[self.env_name]

    # ---- composition -------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Horizontal(
            *(Button(name, id=f"env-{name}") for name in self.manifest.environments),
            id="envbar",
        )
        yield Horizontal(
            Static(id="summary"),
            Static(_PREVIEW_HINT, id="preview"),
            id="top",
        )
        yield VerticalScroll(*self._row_widgets(), id="profiles")
        yield Horizontal(
            Horizontal(*self._test_widgets(), id="tests"),
            Horizontal(*self._scrape_widgets(), id="scrape"),
            id="bottom",
        )
        # wrap=True so long stream-json lines fold to panel width instead of
        # scrolling horizontally off-screen. Click-to-copy still works because
        # each entry is written as a meta-tagged Text: every wrapped strip of an
        # entry carries the same buffer index, so a click resolves it via meta.
        yield ClickCopyLog(id="log", highlight=False, markup=False, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self._render_summary()
        self._update_env_buttons()
        self._write_log(
            "Docker manager ready. Tab to an action to preview it; Enter runs it. "
            "Click a log line to copy it."
        )

    # ---- row construction --------------------------------------------------
    def _scopes(self) -> list[str]:
        return [ALL, *sorted(self.profile_map.keys())]

    def _row_widgets(self) -> list[Horizontal]:
        rows: list[Horizontal] = []
        for scope in self._scopes():
            children: list[Static | Button] = [
                Static(self._row_label(scope), classes="scope-label")
            ]
            children += [
                Button(self._button_label(scope, action), id=f"act-{scope}-{action}")
                for action in ACTIONS
            ]
            rows.append(Horizontal(*children, classes="scope-row"))
        return rows

    def _row_label(self, scope: str) -> str:
        if scope == "bot" and self.env.config_merge is not None:
            return "bot (idles in dev)"
        return scope

    @staticmethod
    def _button_label(scope: str, action: str) -> str:
        if action == "stop":
            return "Down" if scope == ALL else "Stop"
        return action.capitalize()

    def _test_widgets(self) -> list[Static | Button]:
        children: list[Static | Button] = [Static("tests", classes="scope-label")]
        children += [Button(_TEST_LABELS[test], id=f"test-{test}") for test in TESTS]
        return children

    def _scrape_widgets(self) -> list[Static | Button]:
        cfg = load_config_summary(self.env, masked_env())
        children: list[Static | Button] = [Static("scrape site:", classes="scope-label")]
        children += [Button(site, id=f"scrape-{site}") for site in sorted(cfg.enabled_sites)]
        return children

    # ---- events ------------------------------------------------------------
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("env-"):
            await self._switch_env(button_id[len("env-") :])
        elif button_id.startswith("act-"):
            _, scope, action = button_id.split("-", 2)
            self._run_action(scope, action)
        elif button_id.startswith("test-"):
            self._run_test(button_id[len("test-") :])
        elif button_id.startswith("scrape-"):
            self._run_scrape_site(button_id[len("scrape-") :])

    def on_descendant_focus(self, event) -> None:
        widget = getattr(event, "widget", None) or getattr(event, "control", None)
        widget_id = getattr(widget, "id", None) or ""
        if widget_id.startswith("act-"):
            _, scope, action = widget_id.split("-", 2)
            self._preview(scope, action)
        elif widget_id.startswith("test-"):
            self._preview_test(widget_id[len("test-") :])
        elif widget_id.startswith("scrape-"):
            self._preview_scrape(widget_id[len("scrape-") :])

    # ---- actions -----------------------------------------------------------
    def _run_action(self, scope: str, action: str) -> None:
        if self.runner.is_running:
            self._log("! a command is already running — press 'c' to cancel it first")
            return
        sequence = build_sequence(self.env, scope, action, self.profile_map)
        self._preview(scope, action)
        self.run_worker(self._execute(sequence, action), exclusive=True, group="runner")

    def _run_scrape_site(self, site: str) -> None:
        if self.runner.is_running:
            self._log("! a command is already running — press 'c' to cancel it first")
            return
        sequence = build_scrape_site(site)
        self._preview_scrape(site)
        self.run_worker(self._execute(sequence, "test"), exclusive=True, group="runner")

    def _run_test(self, test: str) -> None:
        if self.runner.is_running:
            self._log("! a command is already running — press 'c' to cancel it first")
            return
        sequence = build_test(test)
        self._preview_test(test)
        # action != "start", so _execute skips the proxy-down warn path.
        self.run_worker(self._execute(sequence, "test"), exclusive=True, group="runner")

    async def _execute(self, sequence, action: str) -> None:
        if action == "start" and self.env.proxy is not None:
            await self._warn_if_proxy_down()

        def _write(line: str) -> None:
            self._write_log(str(line))

        await self.runner.run(sequence, _write)

    async def _warn_if_proxy_down(self) -> None:
        host, port = _split_host_port(self.env.proxy.check_url)
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=2.0)
            writer.close()
        except (TimeoutError, OSError, ValueError):
            self._log(
                f"! proxy not reachable at {host}:{port} — "
                "start it or the scraper will fail (continuing anyway)"
            )

    async def action_quit_clean(self) -> None:
        await self.runner.cancel()
        self.exit()

    async def action_cancel(self) -> None:
        if self.runner.is_running:
            self._log("... cancelling (an in-flight build continues inside Docker)")
            await self.runner.cancel()
        else:
            self._log("(nothing running)")

    def action_refresh_status(self) -> None:
        self._run_action(ALL, "status")

    def action_clear_log(self) -> None:
        self._log_buffer.clear()
        self._selected_range = None
        self.query_one("#log", RichLog).clear()

    def action_toggle_log(self) -> None:
        is_visible = self.query_one("#top").display
        for widget_id in ("top", "profiles", "bottom"):
            self.query_one(f"#{widget_id}").display = not is_visible

    def action_copy_log(self) -> None:
        if not self._log_buffer:
            self._log("(log is empty)")
            return
        if self._copy_text("\n".join(self._log_buffer)):
            self._log(f"✓ copied {len(self._log_buffer)} lines to clipboard")

    def on_click_copy_log_range_selected(self, event: ClickCopyLog.RangeSelected) -> None:
        # Live drag updates (final=False) fire on every MouseMove, but the range
        # only changes when the pointer crosses an entry boundary. Repaint ONLY on
        # an actual change: _repaint_log is O(N) over the buffer, so repainting per
        # raw move would make a long drag quadratic. Clamp to the buffer first so a
        # stale row index (e.g. log cleared mid-drag) can never slice out of range.
        n = len(self._log_buffer)
        if n == 0:
            return
        lo = max(0, min(event.lo, n - 1))
        hi = max(0, min(event.hi, n - 1))
        new_range = (lo, hi)
        if new_range != self._selected_range:
            self._selected_range = new_range
            self._repaint_log()
        # Copy on release. This is a SIBLING of the dedupe check above, never
        # nested under it: on release the last MouseMove already set this range, so
        # the range is unchanged here — nesting the copy would silently skip it
        # (and would break single-click, whose down sets (n,n) and up re-sends it).
        if event.final:
            text = "\n".join(self._log_buffer[lo : hi + 1])
            if self._copy_text(text):
                # Transient toast, not a log write: a log write would append a line
                # and (at the bottom) scroll, fighting the selection just made.
                # (Copy *failures* still log via _copy_text — rare and worth a
                # persistent line the user won't miss.)
                count = hi - lo + 1
                if count == 1:
                    self.notify(f"copied line {lo + 1}", timeout=2)
                else:
                    self.notify(f"copied {count} lines ({lo + 1}–{hi + 1})", timeout=2)

    def _copy_text(self, content: str) -> bool:
        """Copy text via the platform clipboard tool; return success, log on failure."""
        try:
            if os.environ.get("WAYLAND_DISPLAY"):
                subprocess.run(["wl-copy"], input=content.encode(), check=True, timeout=3)
            else:
                subprocess.run(
                    ["xclip", "-sel", "clip"], input=content.encode(), check=True, timeout=3
                )
            return True
        except FileNotFoundError as exc:
            self._log(f"! clipboard tool not found: {exc.filename} — install wl-clipboard or xclip")
        except Exception as exc:
            self._log(f"! copy failed: {exc}")
        return False

    # ---- environment switch ------------------------------------------------
    async def _switch_env(self, name: str) -> None:
        if name == self.env_name or name not in self.manifest.environments:
            return
        if self.runner.is_running:
            self._log("! stop the running command before switching environment")
            return
        self.env_name = name
        self.profile_map = compose_mod.parse_profiles(self.env.compose_files)
        container = self.query_one("#profiles", VerticalScroll)
        await container.remove_children()
        await container.mount(*self._row_widgets())
        scrape_container = self.query_one("#scrape", Horizontal)
        await scrape_container.remove_children()
        await scrape_container.mount(*self._scrape_widgets())
        self._render_summary()
        self._update_env_buttons()
        self._set_preview(_PREVIEW_HINT)
        self._log(f"— switched to environment: {name}")

    def _update_env_buttons(self) -> None:
        for name in self.manifest.environments:
            button = self.query_one(f"#env-{name}", Button)
            button.variant = "success" if name == self.env_name else "default"

    # ---- rendering helpers -------------------------------------------------
    def _preview(self, scope: str, action: str) -> None:
        sequence = build_sequence(self.env, scope, action, self.profile_map)
        self._set_preview("\n".join(command.preview() for command in sequence))

    def _preview_test(self, test: str) -> None:
        sequence = build_test(test)
        self._set_preview("\n".join(command.preview() for command in sequence))

    def _preview_scrape(self, site: str) -> None:
        sequence = build_scrape_site(site)
        self._set_preview("\n".join(cmd.preview() for cmd in sequence))

    def _set_preview(self, text: str) -> None:
        self.query_one("#preview", Static).update(text)

    def _render_summary(self) -> None:
        env = self.env
        env_vars = masked_env()
        cfg = load_config_summary(env, env_vars)
        lines = [
            f"[b]env:[/b] {env.name} — {env.description}",
            f"[b]compose:[/b] {' '.join(env.compose_files)}",
            f"[b]config:[/b] {cfg.source_label}",
            f"[b]keywords:[/b] {', '.join(cfg.keywords) or '(none)'}",
            f"[b]sites:[/b] {', '.join(cfg.enabled_sites) or '(none)'}",
            f"[b]proxy:[/b] {cfg.proxy}",
            f"[b]mongo:[/b] {cfg.mongo_db} / {cfg.mongo_collection}",
        ]
        for key in _SUMMARY_ENV_KEYS:
            if key in env_vars:
                lines.append(f"[b]{key}:[/b] {env_vars[key]}")
        self.query_one("#summary", Static).update("\n".join(lines))

    def _styled_line(self, idx: int) -> Text:
        # One buffer entry rendered as a meta-tagged Text. The meta {"row": idx}
        # rides on every cell (and every wrapped strip), so any press/drag over the
        # entry resolves back to this index. Entries inside the selected range ALSO
        # get a high-contrast highlight — combined with `+` so they keep their meta
        # (a bare highlight style would drop "row" and make the line un-copyable).
        style = Style.from_meta({"row": idx})
        selected = self._selected_range
        if selected is not None and selected[0] <= idx <= selected[1]:
            style = style + Style(color="black", bgcolor="yellow", bold=True)
        return Text(self._log_buffer[idx], style=style)

    def _write_log(self, line: str) -> None:
        # Append-only fast path for streaming output: tag with this entry's
        # permanent buffer index, append, then write one meta-tagged Text. An
        # embedded "\n" no longer breaks click-to-copy — wrap shares one meta row
        # across all strips of the entry, so every strip maps to the same index.
        log = self.query_one("#log", RichLog)
        # Tail-follow: keep scrolling to the bottom only if we're already there.
        # If the user scrolled up (e.g. to click-copy a line), leave them put.
        log.auto_scroll = log.scroll_offset.y >= log.max_scroll_y
        idx = len(self._log_buffer)
        self._log_buffer.append(line)
        log.write(self._styled_line(idx))

    def _repaint_log(self) -> None:
        # Full re-render, called only on selection change (never per write) so
        # streaming stays append-only. Re-writes every buffer entry, highlighting
        # the selected one. auto_scroll is forced off during the rewrite so the
        # tail-follow doesn't clobber the restored scroll position.
        #
        # Safe because every writer (this method + _write_log) runs on the event
        # loop with no threads (runner streams via `async for` on the loop), so
        # nothing can append between clear() and the rewrite loop below. A future
        # threaded log callback would break that and must re-establish it.
        log = self.query_one("#log", RichLog)
        saved_y = log.scroll_offset.y
        log.clear()
        log.auto_scroll = False
        for idx in range(len(self._log_buffer)):
            log.write(self._styled_line(idx))
        log.scroll_to(y=saved_y, animate=False)

    def _log(self, message: str) -> None:
        self._write_log(message)


def _split_host_port(url: str) -> tuple[str, int]:
    """'socks5://localhost:1080' -> ('localhost', 1080)."""
    without_scheme = url.split("://", 1)[-1]
    host, _, port = without_scheme.partition(":")
    return host or "localhost", int(port or "1080")
