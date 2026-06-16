## File Name: control_panel.py
## Description: LocalMind Control Panel — Terminal 2 TUI
## Path: scripts/control_panel.py
## Created By: Lokesh R     Created On: 2026-06-16

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.dirname(__file__))

import threading
import time
import json

from textual.app import App, ComposeResult
from textual.widgets import Static, Input, Footer, Label
from textual.containers import ScrollableContainer, Container
from textual.binding import Binding

import panel_bridge as bridge

INSTRUCTIONS = {
    bridge.STEP_QUERY_SELECT: (
        "LocalMind rewrote your query 3 ways to improve search results.\n"
        "Pick the version that best matches what you want to find.\n"
        "Tip: choose the one with the most specific keywords.\n"
        "Type 1, 2, or 3 and press Enter."
    ),
    bridge.STEP_LINK_SELECT: (
        "These are the web pages found for your query.\n"
        "Select which ones to scrape for information.\n"
        "Tip: 2–4 focused sources gives better answers than scraping everything.\n"
        "Type numbers separated by commas (e.g. 1,3) or A for all, then Enter."
    ),
    bridge.STEP_SECTION_SELECT: (
        "This is the scraped content from the selected page.\n"
        "Select which sections contain the information you need.\n"
        "Tip: too many sections slows the model and reduces answer quality.\n"
        "Pick 2–4 focused sections. Type numbers (e.g. 1,3) or A for all, then Enter."
    ),
    bridge.STEP_GENERATING: (
        "The model is generating a response from your selected content.\n"
        "Response will appear in the main LocalMind window.\n"
        "Press Ctrl+S in the main window to stop generation."
    ),
    bridge.STEP_IDLE: (
        "Waiting for a query in the main LocalMind window..."
    ),
    bridge.STEP_DONE: (
        "Response complete. Ask another question in the main window."
    ),
    bridge.STEP_ERROR: (
        "Something went wrong. Check the main LocalMind window for details."
    ),
}

class ControlPanel(App):

    CSS = """
    Screen { background: #0a0a0a; }

    #header {
        height: 3;
        content-align: center middle;
        text-align: center;
        color: #02C39A;
        border-bottom: solid #1E2761;
    }

    #step-bar {
        height: 1;
        text-align: center;
        color: #028090;
        margin: 0 1;
    }

    #instruction-box {
        height: auto;
        min-height: 5;
        border: solid #f0a500;
        margin: 1 1 0 1;
        padding: 0 1;
        color: #f0a500;
    }

    #content-scroll {
        height: 1fr;
        border: solid #1E2761;
        margin: 1 1 0 1;
        padding: 1;
        overflow-y: auto;
    }

    .item { padding: 0 1; margin-bottom: 1; color: white; }
    .item-title { color: #02C39A; }
    .item-snippet { color: #888888; }
    .item-meta { color: #555555; }

    #input-container {
        height: auto;
        margin: 1 1;
        border: solid #028090;
        padding: 0 1;
    }

    #selection-input {
        background: #0a0a0a;
        color: white;
        border: none;
    }

    #status-bar {
        height: 1;
        text-align: center;
        color: #444444;
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit Panel", priority=True),
    ]

    def __init__(self):
        super().__init__()
        self._last_trigger  = None
        self._current_step  = bridge.STEP_IDLE
        self._current_data  = []
        self._waiting_input = False
        self._heartbeat_thread = None
        self._poll_thread      = None

    def compose(self) -> ComposeResult:
        yield Label(
            "LocalMind Control Panel",
            id="header"
        )
        yield Label("", id="step-bar")
        yield Static(
            INSTRUCTIONS[bridge.STEP_IDLE],
            id="instruction-box",
            markup=False
        )
        yield ScrollableContainer(
            Static("", id="content-area", markup=True),
            id="content-scroll"
        )
        yield Label("", id="status-bar")
        yield Container(
            Input(
                placeholder="Waiting...",
                id="selection-input"
            ),
            id="input-container"
        )
        yield Footer()

    def on_mount(self):
        ## clean stale files and signal ready
        bridge.clean_all()
        self._signal_ready()

        ## start heartbeat thread
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True
        )
        self._heartbeat_thread.start()

        ## start bridge poll thread
        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True
        )
        self._poll_thread.start()

        self.query_one("#selection-input").focus()

    def _signal_ready(self):
        with open(bridge.READY_FILE, "w") as f:
            f.write("ready")

    def _heartbeat_loop(self):
        while True:
            bridge.panel_heartbeat()
            time.sleep(1)

    def _poll_loop(self):
        ## watches trigger file and updates UI when terminal 1 writes new state
        while True:
            try:
                mtime = bridge.get_trigger_mtime()
                if mtime != self._last_trigger and mtime is not None:
                    self._last_trigger = mtime
                    state = bridge.read_state()
                    if state:
                        self.call_from_thread(self._handle_state, state)
            except:
                pass
            time.sleep(0.2)

    def _handle_state(self, state):
        step  = state.get("step", bridge.STEP_IDLE)
        data  = state.get("data", [])
        instr = state.get("instruction", INSTRUCTIONS.get(step, ""))
        meta  = state.get("meta", {})

        self._current_step = step
        self._current_data = data

        ## update step bar
        step_labels = {
            bridge.STEP_IDLE:           "○ Idle",
            bridge.STEP_QUERY_SELECT:   "● Step 1 — Query Selection",
            bridge.STEP_LINK_SELECT:    "● Step 2 — Link Selection",
            bridge.STEP_SECTION_SELECT: "● Step 3 — Section Selection",
            bridge.STEP_GENERATING:     "● Step 4 — Generating Response",
            bridge.STEP_DONE:           "✓ Done",
            bridge.STEP_ERROR:          "✗ Error",
        }
        self.query_one("#step-bar", Label).update(step_labels.get(step, step))

        ## update instruction box
        self.query_one("#instruction-box", Static).update(
            instr or INSTRUCTIONS.get(step, "")
        )

        ## update content area
        content_widget = self.query_one("#content-area", Static)
        content_widget.update(self._render_data(step, data, meta))
        self.query_one("#content-scroll", ScrollableContainer).scroll_home(animate=False)

        ## update input placeholder and interactivity
        inp = self.query_one("#selection-input", Input)

        if step == bridge.STEP_QUERY_SELECT:
            inp.placeholder = "Type 1, 2 or 3 and press Enter..."
            inp.disabled = False
            self._waiting_input = True
            inp.focus()

        elif step in [bridge.STEP_LINK_SELECT, bridge.STEP_SECTION_SELECT]:
            inp.placeholder = "e.g. 1,3  or  A for all — then Enter..."
            inp.disabled = False
            self._waiting_input = True
            inp.focus()

        elif step in [bridge.STEP_GENERATING, bridge.STEP_IDLE,
                      bridge.STEP_DONE, bridge.STEP_ERROR]:
            inp.placeholder = "Waiting for main window..."
            inp.disabled = True
            self._waiting_input = False

        ## update status bar
        if meta.get("status"):
            self.query_one("#status-bar", Label).update(meta["status"])
        else:
            self.query_one("#status-bar", Label).update("")

    def _render_data(self, step, data, meta):
        if not data:
            return "[dim]Nothing to show yet[/dim]"

        lines = []

        if step == bridge.STEP_QUERY_SELECT:
            lines.append("[bold]Choose a search query:[/bold]\n")
            for item in data:
                n = item["index"]
                q = item["query"]
                lines.append(f"  [bold cyan][ {n} ][/bold cyan]  {q}\n")

        elif step == bridge.STEP_LINK_SELECT:
            lines.append(
                f"[bold]Found {len(data)} link(s) — select which to scrape:[/bold]\n"
            )
            for item in data:
                n       = item["index"]
                title   = item["title"]
                url     = item["url"]
                snippet = item.get("snippet", "")
                lines.append(
                    f"  [bold cyan][ {n} ][/bold cyan]  "
                    f"[bold]{title}[/bold]\n"
                    f"        [dim]{url}[/dim]\n"
                )
                if snippet:
                    lines.append(f"        [#888888]{snippet[:200]}[/#888888]\n")
                lines.append("\n")

        elif step == bridge.STEP_SECTION_SELECT:
            site = meta.get("site_title", "")
            if site:
                lines.append(f"[bold]Page:[/bold] {site}\n\n")
            lines.append(
                f"[bold]Found {len(data)} section(s) — select which to feed:[/bold]\n\n"
            )
            for item in data:
                n       = item["index"]
                title   = item.get("title", f"Section {n}")
                words   = item.get("word_count", 0)
                content = item.get("content", "")
                lines.append(
                    f"  [bold cyan][ {n} ][/bold cyan]  "
                    f"[bold]{title}[/bold]  "
                    f"[dim]({words} words)[/dim]\n\n"
                )
                ## show full content, wrapped at ~80 chars
                if content:
                    lines.append(f"[#cccccc]{content}[/#cccccc]\n\n")
                lines.append("[dim]" + "─"*56 + "[/dim]\n\n")

        elif step == bridge.STEP_GENERATING:
            sources = meta.get("sources", [])
            sections_count = meta.get("sections_count", 0)
            lines.append(
                f"[bold green]Generating response from "
                f"{sections_count} section(s) across "
                f"{len(sources)} source(s)[/bold green]\n\n"
            )
            for s in sources:
                lines.append(f"  [cyan]✓[/cyan] {s}\n")

        elif step == bridge.STEP_DONE:
            lines.append("[bold green]✓ Response complete.[/bold green]\n")
            lines.append("[dim]Ask another question in the main window.[/dim]\n")

        elif step == bridge.STEP_ERROR:
            msg = meta.get("error", "Unknown error")
            lines.append(f"[bold red]✗ {msg}[/bold red]\n")

        return "".join(lines)

    def on_input_submitted(self, event: Input.Submitted):
        if not self._waiting_input:
            return

        raw = event.value.strip()
        self.query_one("#selection-input", Input).value = ""

        if not raw:
            return

        step = self._current_step
        data = self._current_data

        ## ── query select ──────────────────────────────────────────
        if step == bridge.STEP_QUERY_SELECT:
            if raw not in ["1", "2", "3"]:
                self._set_status("[red]Please type 1, 2 or 3[/red]")
                return
            chosen_index = int(raw)
            chosen = next(
                (d for d in data if d["index"] == chosen_index), None
            )
            if not chosen:
                self._set_status("[red]Invalid selection[/red]")
                return
            self._waiting_input = False
            self.query_one("#selection-input", Input).disabled = True
            self._set_status(f"[green]✓ Query {chosen_index} selected[/green]")
            bridge.write_result({"type": "query", "selected": chosen["query"]})

        ## ── link select ───────────────────────────────────────────
        elif step == bridge.STEP_LINK_SELECT:
            selected = self._parse_selection(raw, len(data))
            if selected is None:
                self._set_status("[red]Invalid — use numbers like 1,3 or A for all[/red]")
                return
            self._waiting_input = False
            self.query_one("#selection-input", Input).disabled = True
            label = "all" if len(selected) == len(data) else str(selected)
            self._set_status(f"[green]✓ Links {label} selected[/green]")
            bridge.write_result({"type": "links", "selected": selected})

        ## ── section select ────────────────────────────────────────
        elif step == bridge.STEP_SECTION_SELECT:
            selected = self._parse_selection(raw, len(data))
            if selected is None:
                self._set_status("[red]Invalid — use numbers like 1,3 or A for all[/red]")
                return
            self._waiting_input = False
            self.query_one("#selection-input", Input).disabled = True
            label = "all" if len(selected) == len(data) else str(selected)
            self._set_status(f"[green]✓ Sections {label} selected[/green]")
            bridge.write_result({"type": "sections", "selected": selected})

    def _parse_selection(self, raw, total):
        ## returns list of ints or None on invalid input
        if raw.lower() == "a":
            return list(range(1, total + 1))
        try:
            selected = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
            if not selected:
                return None
            if any(s < 1 or s > total for s in selected):
                return None
            return selected
        except:
            return None

    def _set_status(self, text):
        self.query_one("#status-bar", Label).update(text)

    def action_quit(self):
        bridge.clean_all()
        self.exit()


if __name__ == "__main__":
    app = ControlPanel()
    app.run()