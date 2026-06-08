## File Name: localmind.py
## Description: LocalMind TUI - Interactive Terminal UI with model selector
## Path: localmind.py
## Created By: Lokesh R     Created On: 2026-05-25
## Updated By: Lokesh R     Updated On: 2026-06-02
## Fixed / menu bug, model selector working correctly

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "scripts"))

from textual.app import App, ComposeResult
from textual.widgets import Input, Footer, Label, OptionList, Static
from textual.widgets.option_list import Option
from textual.containers import Container, ScrollableContainer
from textual.binding import Binding
from pipeline import ask_localmind
import threading
import time
import requests
import json

## ── model utilities ──────────────────────────────────────────────────────

def get_installed_models():
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        data = response.json()
        models = []
        for m in data.get("models", []):
            size_gb = round(m["size"] / 1e9, 1)
            param = m["details"].get("parameter_size", "?")
            quant = m["details"].get("quantization_level", "?")
            ram_needed = round(size_gb * 1.2, 1)
            models.append({
                "name": m["name"],
                "size_gb": size_gb,
                "param": param,
                "quant": quant,
                "ram_needed": ram_needed,
            })
        return models
    except:
        return []

class LocalMind(App):

    CSS = """
    Screen { background: #0a0a0a; }

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

    .message { padding: 0 1; margin-bottom: 1; }

    #input-container {
        height: auto;
        margin: 1 1;
        border: solid #028090;
        padding: 0 1;
    }

    #query { background: #0a0a0a; color: white; border: none; }

    #status {
        text-align: center;
        color: #028090;
        height: 1;
        margin: 0 1;
    }

    #command-menu {
        display: none;
        position: absolute;
        width: 70%;
        height: auto;
        max-height: 16;
        margin: 0 1;
        border: solid #028090;
        background: #111111;
        layer: above;
    }

    #command-menu.visible { display: block; }

    #model-menu {
        display: none;
        position: absolute;
        width: 80%;
        height: auto;
        max-height: 16;
        margin: 0 1;
        border: solid #02C39A;
        background: #111111;
        layer: above;
    }

    #model-menu.visible { display: block; }
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
        self.current_model = "mistral:latest"
        self.installed_models = []
        self._showing_model_menu = False

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
            "● Local mode  |  model: mistral:latest  |  type / for commands  |  ctrl+s stop  |  ctrl+c quit",
            id="status"
        )
        yield Container(
            Input(placeholder='Ask anything... (type / for commands)', id="query"),
            id="input-container"
        )
        yield OptionList(
            Option("/web       — Enable web search", id="web"),
            Option("/local     — Switch to local mode", id="local"),
            Option("/models    — Select AI model", id="models"),
            Option("/links     — Set number of sites to search", id="links"),
            Option("/clear     — Clear chat", id="clear"),
            Option("/exit      — Exit LocalMind", id="exit"),
            id="command-menu"
        )
        yield OptionList(id="model-menu")
        yield Footer()

    def on_mount(self):
        self.query_one("#query").focus()
        threading.Thread(target=self._load_models, daemon=True).start()

    def _load_models(self):
        self.installed_models = get_installed_models()
        if self.installed_models:
            self.current_model = self.installed_models[0]["name"]
            self.call_from_thread(self._update_status)
            self.call_from_thread(
                self._add_message_main,
                f"[dim]✓ Found {len(self.installed_models)} model(s) — using [bold]{self.current_model}[/bold][/dim]"
            )
        else:
            self.call_from_thread(
                self._add_message_main,
                "[bold red]⚠ No Ollama models found — make sure Ollama is running[/bold red]"
            )

    def _update_status(self):
        mode = "Web search ON" if self.web_search else "Local mode"
        self.query_one("#status", Label).update(
            f"● {mode}  |  model: {self.current_model}  |  type / for commands  |  ctrl+s stop  |  ctrl+c quit"
        )

    def _show_model_menu(self):
        self._showing_model_menu = True
        menu = self.query_one("#model-menu", OptionList)
        menu.clear_options()

        if not self.installed_models:
            self._add_message_main(
                "[bold red]No models found. Run: ollama pull mistral[/bold red]"
            )
            self._showing_model_menu = False
            return

        for m in self.installed_models:
            prefix = "● " if m["name"] == self.current_model else "  "
            display = f"{prefix}{m['name']}  —  {m['param']} · {m['quant']} · {m['size_gb']}GB · ~{m['ram_needed']}GB RAM"
            menu.add_option(Option(display, id=f"model__{m['name']}"))

        menu.add_option(Option("  ── cancel ──", id="model__cancel"))
        self.query_one("#command-menu", OptionList).remove_class("visible")
        menu.add_class("visible")
        menu.focus()

    ## ── helpers ──────────────────────────────────────────────────────────

    def _add_message_main(self, text, markup=True):
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
        ## hide model menu when typing
        if self._showing_model_menu:
            return

        cmd_menu = self.query_one("#command-menu", OptionList)
        model_menu = self.query_one("#model-menu", OptionList)
        model_menu.remove_class("visible")

        if event.value == "/":
            cmd_menu.add_class("visible")
            cmd_menu.focus()
        else:
            cmd_menu.remove_class("visible")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        option_id = event.option.id

        ## ── model menu selection ──────────────────────────────────────
        if event.option_list.id == "model-menu":
            self._showing_model_menu = False
            self.query_one("#model-menu", OptionList).remove_class("visible")
            self.query_one("#query").value = ""
            self.query_one("#query").focus()

            selected_model = option_id.replace("model__", "")
            if selected_model == "cancel":
                return

            self.current_model = selected_model
            self._update_status()

            for m in self.installed_models:
                if m["name"] == selected_model:
                    self._add_message_main(
                        f"[bold green]✓ Switched to [bold]{selected_model}[/bold][/bold green]\n"
                        f"[dim]  {m['param']} · {m['quant']} · {m['size_gb']}GB · needs ~{m['ram_needed']}GB RAM[/dim]"
                    )
                    break
            return

        ## ── command menu selection ────────────────────────────────────
        self.query_one("#command-menu", OptionList).remove_class("visible")
        self.query_one("#query").value = ""
        self.query_one("#query").focus()

        if option_id == "web":
            self.web_search = True
            self._update_status()
            self._add_message_main("[bold green]✓ Web search enabled[/bold green]")

        elif option_id == "local":
            self.web_search = False
            self._update_status()
            self._add_message_main("[bold yellow]✓ Local mode enabled[/bold yellow]")

        elif option_id == "models":
            self._show_model_menu()

        elif option_id == "links":
            self._add_message_main(
                "[bold yellow]Type /links 3 or /links 5 to set number of sites (1-10)[/bold yellow]"
            )

        elif option_id == "clear":
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            scroll.remove_children()
            scroll.mount(Static(
                "[bold cyan]LocalMind[/bold cyan] [dim]— chat cleared[/dim]",
                classes="message", markup=True
            ))

        elif option_id == "exit":
            self.exit()

    def action_hide_menu(self):
        self._showing_model_menu = False
        self.query_one("#command-menu", OptionList).remove_class("visible")
        self.query_one("#model-menu", OptionList).remove_class("visible")
        self.query_one("#query").value = ""
        self.query_one("#query").focus()

    def action_stop(self):
        if self.is_generating:
            self.stop_flag = True
            self._add_message_main("[bold red]⏹ Generation stopped[/bold red]")
            self.is_generating = False

    def on_input_submitted(self, event: Input.Submitted):
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
                    self._update_status()
                    self._add_message_main(
                        f"[bold green]✓ Will search top {n} sites[/bold green]"
                    )
                else:
                    self._add_message_main(
                        "[bold red]Please enter a number between 1 and 10[/bold red]"
                    )
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
        self.is_generating = True
        self.stop_flag = False
        start = time.time()

        def progress(msg):
            self.call_from_thread(self._add_message_main, msg)

        def chunk_callback(action, data):
            if self.stop_flag:
                return None
            if action == "start":
                return self.call_from_thread(self._add_message_main, data)
            elif action == "token":
                self.call_from_thread(self._update_message, data["id"], data["text"])
            return None

        def stop_check():
            return self.stop_flag

        sources = ask_localmind(
            query,
            max_links=self.max_links,
            progress_callback=progress,
            chunk_callback=chunk_callback,
            stop_flag=stop_check,
            model=self.current_model
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
            self._add_message_main,
            f"[dim cyan]🤖 Thinking with {self.current_model}...[/dim cyan]"
        )

        answer = ""
        msg_id = self.call_from_thread(
            self._add_message_main, "[bold cyan]LocalMind:[/bold cyan] "
        )

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": self.current_model,
                    "prompt": query,
                    "stream": True,
                    "keep_alive": -1,
                    "options": {
                        "num_predict": 1024,
                        "temperature": 0.3,
                        "num_ctx": 2048
                    }
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