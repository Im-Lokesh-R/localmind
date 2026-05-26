## File Name: localmind.py
## Description: LocalMind TUI - Interactive Terminal UI
## Path: localmind.py
## Created By: Lokesh R     Created On: 2026-05-25

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "scripts"))

from textual.app import App, ComposeResult
from textual.widgets import Input, Footer, Label, OptionList, Static
from textual.widgets.option_list import Option
from textual.containers import Container, ScrollableContainer
from textual.binding import Binding
import threading
import time
import requests
import json

class LocalMind(App):

    CSS = """
    Screen {
        background: #0a0a0a;
    }

    #logo {
        content-align: center middle;
        text-align: center;
        color: #02C39A;
        padding: 1 0;
        height: 3;
    }

    #chat-scroll {
        height: 1fr;
        border: solid #1E2761;
        margin: 0 1;
        padding: 1;
        overflow-y: auto;
    }

    .message {
        padding: 0 1;
        margin-bottom: 1;
    }

    #input-container {
        height: auto;
        margin: 1 1;
        border: solid #028090;
        padding: 0 1;
    }

    #query {
        background: #0a0a0a;
        color: white;
        border: none;
    }

    #status {
        text-align: center;
        color: #028090;
        height: 1;
        margin: 0 1;
    }

    #command-menu {
        display: none;
        position: absolute;
        width: 50%;
        height: auto;
        max-height: 12;
        margin: 0 1;
        border: solid #028090;
        background: #111111;
        layer: above;
    }

    #command-menu.visible {
        display: block;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+s", "stop", "Stop"),
        Binding("escape", "hide_menu", "Close menu"),
    ]

    def __init__(self):
        super().__init__()
        self.web_search = False
        self.max_links = 5
        self.is_generating = False
        self.stop_flag = False
        self._current_msg_id = 0

    def compose(self) -> ComposeResult:
        yield Label("LocalMind  —  Privacy-First Research Assistant", id="logo")
        yield ScrollableContainer(
            Static(
                "[bold cyan]LocalMind[/bold cyan] [dim]— type anything to start[/dim]",
                classes="message", markup=True
            ),
            id="chat-scroll"
        )
        yield Label(
            "● Local mode  |  type / for commands  |  ctrl+s stop  |  ctrl+c quit",
            id="status"
        )
        yield Container(
            Input(placeholder='Ask anything... (type / for commands)', id="query"),
            id="input-container"
        )
        yield OptionList(
            Option("/web     — Enable web search", id="web"),
            Option("/local   — Switch to local mode", id="local"),
            Option("/links   — Set number of sites to search", id="links"),
            Option("/clear   — Clear chat", id="clear"),
            Option("/exit    — Exit LocalMind", id="exit"),
            id="command-menu"
        )
        yield Footer()

    def on_mount(self):
        self.query_one("#query").focus()

    ## ── helpers ──────────────────────────────────────────────────────────

    def _add_message(self, text, markup=True):
        ## call directly on main thread, call_from_thread from background
        self._current_msg_id += 1
        msg_id = f"msg-{self._current_msg_id}"
        widget = Static(text, classes="message", markup=markup, id=msg_id)
        scroll = self.query_one("#chat-scroll", ScrollableContainer)
        self.app.call_later(scroll.mount, widget)
        self.app.call_later(scroll.scroll_end, animate=False)
        return msg_id

    def _add_message_main(self, text, markup=True):
        ## safe to call directly from main thread
        self._current_msg_id += 1
        msg_id = f"msg-{self._current_msg_id}"
        widget = Static(text, classes="message", markup=markup, id=msg_id)
        scroll = self.query_one("#chat-scroll", ScrollableContainer)
        scroll.mount(widget)
        scroll.scroll_end(animate=False)
        return msg_id

    def _update_message(self, msg_id, text):
        try:
            widget = self.query_one(f"#{msg_id}", Static)
            widget.update(text)
            self.query_one("#chat-scroll", ScrollableContainer).scroll_end(animate=False)
        except:
            pass

    ## ── events ───────────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed):
        menu = self.query_one("#command-menu", OptionList)
        if event.value == "/":
            menu.add_class("visible")
        else:
            menu.remove_class("visible")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        ## runs on main thread — use _add_message_main
        menu = self.query_one("#command-menu", OptionList)
        menu.remove_class("visible")
        self.query_one("#query").value = ""
        self.query_one("#query").focus()
        selected = event.option.id

        if selected == "web":
            self.web_search = True
            self.query_one("#status", Label).update(
                f"● Web search ON  ({self.max_links} sites)  |  type / for commands  |  ctrl+s stop  |  ctrl+c quit"
            )
            self._add_message_main("[bold green]✓ Web search enabled[/bold green]")

        elif selected == "local":
            self.web_search = False
            self.query_one("#status", Label).update(
                "● Local mode  |  type / for commands  |  ctrl+s stop  |  ctrl+c quit"
            )
            self._add_message_main("[bold yellow]✓ Local mode enabled[/bold yellow]")

        elif selected == "links":
            self._add_message_main(
                "[bold yellow]Type /links 3 or /links 5 to set number of sites (1-10)[/bold yellow]"
            )

        elif selected == "clear":
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            scroll.remove_children()
            scroll.mount(Static(
                "[bold cyan]LocalMind[/bold cyan] [dim]— chat cleared[/dim]",
                classes="message", markup=True
            ))

        elif selected == "exit":
            self.exit()

    def action_hide_menu(self):
        self.query_one("#command-menu", OptionList).remove_class("visible")
        self.query_one("#query").value = ""
        self.query_one("#query").focus()

    def action_stop(self):
        ## runs on main thread — use _add_message_main
        if self.is_generating:
            self.stop_flag = True
            self._add_message_main("[bold red]⏹ Generation stopped[/bold red]")
            self.is_generating = False

    def on_input_submitted(self, event: Input.Submitted):
        ## runs on main thread — use _add_message_main
        if self.is_generating:
            return

        query = event.value.strip()
        if not query or query == "/":
            return

        self.query_one("#query").value = ""

        if query.startswith("/links "):
            try:
                n = int(query.split(" ")[1])
                if 1 <= n <= 10:
                    self.max_links = n
                    self.query_one("#status", Label).update(
                        f"● {'Web search ON' if self.web_search else 'Local mode'}  ({n} sites)  |  type / for commands  |  ctrl+s stop  |  ctrl+c quit"
                    )
                    self._add_message_main(f"[bold green]✓ Will search top {n} sites[/bold green]")
                else:
                    self._add_message_main("[bold red]Please enter a number between 1 and 10[/bold red]")
            except:
                self._add_message_main("[bold red]Usage: /links 3[/bold red]")
            return

        self._add_message_main(f"[bold white]You:[/bold white] {query}")

        if self.web_search:
            threading.Thread(target=self.run_search, args=(query,), daemon=True).start()
        else:
            threading.Thread(target=self.run_local, args=(query,), daemon=True).start()

    ## ── background workers ───────────────────────────────────────────────

    def run_search(self, query):
        from search import search_links
        from scraper import scrape_text

        self.is_generating = True
        self.stop_flag = False
        start = time.time()

        self.call_from_thread(self._add_message_main, "[dim cyan]🔍 Finding sources...[/dim cyan]")

        links = search_links(query, max_results=self.max_links)
        sources = []

        for i, link in enumerate(links):
            if self.stop_flag:
                break

            self.call_from_thread(
                self._add_message_main,
                f"[dim]→ [{i+1}/{len(links)}] visiting {link['url'][:65]}...[/dim]"
            )

            text = scrape_text(link["url"])
            if not text:
                continue

            sources.append(link["title"])
            sources.append(link["url"])

            self.call_from_thread(
                self._add_message_main,
                f"[dim green]  ✓ scraped {link['title'][:50]}[/dim green]"
            )

            word_count = len(text.split())
            estimated = round((word_count / 500) * 12)

            self.call_from_thread(
                self._add_message_main,
                f"[dim]📊 {word_count} words  |  ⏳ ~{estimated}s estimated[/dim]"
            )
            self.call_from_thread(
                self._add_message_main,
                f"[dim cyan]🤖 Generating from source {i+1}...[/dim cyan]"
            )

            prompt = f"""You are a detailed research assistant.
Organize and present ALL the information from this source clearly and comprehensively.
Do NOT summarize. Present in full detail with proper headings.
Only use the context provided.

Source: {link['title']}
Context:
{text[:6000]}

Question:
{query}

Detailed answer:"""

            ## stream this source
            source_answer = ""
            msg_id = self.call_from_thread(
                self._add_message_main,
                f"[bold cyan]LocalMind [{i+1}]:[/bold cyan] "
            )

            try:
                response = requests.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": "mistral",
                        "prompt": prompt,
                        "stream": True,
                        "keep_alive": -1,
                        "options": {"num_predict": 1024, "temperature": 0.3}
                    },
                    stream=True
                )

                for line in response.iter_lines():
                    if self.stop_flag:
                        break
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        token = chunk.get("response", "")
                        source_answer += token
                        self.call_from_thread(
                            self._update_message,
                            msg_id,
                            f"[bold cyan]LocalMind [{i+1}]:[/bold cyan] {source_answer}"
                        )
                        if chunk.get("done"):
                            break

            except Exception as e:
                self.call_from_thread(
                    self._add_message_main, f"[bold red]Error: {e}[/bold red]"
                )

        elapsed = round(time.time() - start, 1)
        self.call_from_thread(self._add_message_main, f"[dim]⏱ Total: {elapsed}s[/dim]")

        if sources:
            src_text = "\n[bold blue]Sources:[/bold blue]\n"
            seen = set()
            count = 1
            for i in range(0, len(sources), 2):
                url = sources[i+1] if i+1 < len(sources) else ""
                title = sources[i]
                if url not in seen:
                    seen.add(url)
                    src_text += f"  [cyan]{count}.[/cyan] {title} [dim]{url}[/dim]\n"
                    count += 1
            self.call_from_thread(self._add_message_main, src_text)

        self.is_generating = False

    def run_local(self, query):
        self.is_generating = True
        self.stop_flag = False
        start = time.time()

        self.call_from_thread(
            self._add_message_main, "[dim cyan]🤖 Thinking locally...[/dim cyan]"
        )

        answer = ""
        msg_id = self.call_from_thread(
            self._add_message_main, "[bold cyan]LocalMind:[/bold cyan] "
        )

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "mistral",
                    "prompt": query,
                    "stream": True,
                    "keep_alive": -1,
                    "options": {"num_predict": 2048, "temperature": 0.3}
                },
                stream=True
            )

            for line in response.iter_lines():
                if self.stop_flag:
                    break
                if line:
                    chunk = json.loads(line.decode("utf-8"))
                    token = chunk.get("response", "")
                    answer += token
                    self.call_from_thread(
                        self._update_message,
                        msg_id,
                        f"[bold cyan]LocalMind:[/bold cyan] {answer}"
                    )
                    if chunk.get("done"):
                        break

        except Exception as e:
            self.call_from_thread(
                self._add_message_main, f"[bold red]Error: {e}[/bold red]"
            )

        elapsed = round(time.time() - start, 1)
        self.call_from_thread(self._add_message_main, f"[dim]⏱ {elapsed}s[/dim]")
        self.is_generating = False

if __name__ == "__main__":
    app = LocalMind()
    app.run()