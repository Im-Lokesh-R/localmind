## File Name: localmind.py
## Description: LocalMind TUI - Interactive Terminal UI with model selector and chat memory
## Path: localmind.py
## Created By: Lokesh R     Created On: 2026-05-25
## Updated By: Lokesh R     Updated On: 2026-06-16
## Fixed: persistent section viewer, trigger file, feed size input, stop flag, msg_id bridge

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "scripts"))

from memory import save_message, build_context, new_session, list_sessions
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
import subprocess
import tempfile

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

def build_local_prompt(query, history, model):
    model_lower = model.lower()
    if "tinyllama" in model_lower or ":1b" in model_lower:
        if history:
            return f"{history}\nQ: {query}\nA:"
        return f"Q: {query}\nA:"
    elif any(x in model_lower for x in ["3b", "phi", "gemma"]):
        if history:
            return f"{history}\nUser: {query}\nAssistant:"
        return f"User: {query}\nAssistant:"
    else:
        if history:
            return f"{history}\nUser: {query}\nLocalMind:"
        return query


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
        max-height: 20;
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
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("ctrl+s", "stop", "Stop", priority=True, show=True),
        Binding("escape", "hide_menu", "Close menu"),
    ]

    def __init__(self):
        super().__init__()
        self.session_id      = new_session()
        self.web_search      = False
        self.max_links       = 5
        self.feed_size       = 1500
        self.is_generating   = False
        self._stop_event     = threading.Event()
        self._current_msg_id = 0
        self._msg_id_lock    = threading.Lock()
        self.current_model   = "mistral:latest"
        self.installed_models = []
        self._showing_model_menu = False
        self._last_web_answer    = ""
        self._setting_feed       = False

        ## section viewer temp files
        self._viewer_proc   = None
        self._sections_file = os.path.join(tempfile.gettempdir(), "localmind_sections.json")
        self._result_file   = os.path.join(tempfile.gettempdir(), "localmind_selection.json")
        self._ready_file    = os.path.join(tempfile.gettempdir(), "localmind_viewer_ready.txt")
        self._trigger_file  = os.path.join(tempfile.gettempdir(), "localmind_trigger.txt")

    ## ── section viewer ────────────────────────────────────────────

    def _launch_section_viewer(self):
        ## FIX: check if the actual Python viewer process is still alive
        ## cmd /c start exits immediately so poll() was always returning "dead"
        ## now we launch Python directly with CREATE_NEW_CONSOLE so proc IS the viewer
        if self._viewer_proc is not None and self._viewer_proc.poll() is None:
            return  ## already running, don't relaunch

        ## clean up stale temp files
        for f in [self._sections_file, self._result_file,
                  self._ready_file, self._trigger_file]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except:
                    pass

        viewer_script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "scripts", "section_viewer.py"
        )

        try:
            ## FIX: launch Python directly with CREATE_NEW_CONSOLE
            ## this gives it its own visible window AND proc is the actual process
            ## so poll() correctly tells us if the viewer is still open
            self._viewer_proc = subprocess.Popen(
                [
                    sys.executable, viewer_script,
                    self._sections_file,
                    self._result_file,
                    self._ready_file,
                    self._trigger_file
                ],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        except Exception as e:
            self._add_message_main(
                f"[bold red]⚠ Could not open section viewer: {e}[/bold red]"
            )

    def _section_picker(self, page_title, sections):
        ## FIX: poll() now works correctly since proc IS the viewer Python process
        if self._viewer_proc is None or self._viewer_proc.poll() is not None:
            self.call_from_thread(
                self._add_message_main,
                "[dim yellow]⚠ Section viewer closed — reopening...[/dim yellow]"
            )
            ## FIX: call directly, not via call_from_thread — safe from bg thread
            self._launch_section_viewer()

            ## wait for ready file
            waited = 0
            while not os.path.exists(self._ready_file) and waited < 10:
                if self._stop_event.is_set():
                    return None
                time.sleep(0.3)
                waited += 0.3

        ## clear old result
        if os.path.exists(self._result_file):
            try:
                os.remove(self._result_file)
            except:
                pass

        ## write sections fully first, then trigger
        sections_data = {"title": page_title, "sections": sections}
        with open(self._sections_file, "w", encoding="utf-8") as f:
            json.dump(sections_data, f, ensure_ascii=False)

        time.sleep(0.1)  ## ensure flush before trigger

        with open(self._trigger_file, "w") as f:
            f.write(str(time.time()))

        self.call_from_thread(
            self._add_message_main,
            f"[dim cyan]📄 {page_title[:45]} — {len(sections)} sections → select in viewer[/dim cyan]"
        )

        ## poll for result
        waited = 0
        while waited < 60:
            if self._stop_event.is_set():
                return None
            if os.path.exists(self._result_file):
                for _ in range(3):
                    try:
                        with open(self._result_file, "r", encoding="utf-8") as f:
                            result = json.load(f)
                        selected = result.get("selected", [])
                        if selected:
                            self.call_from_thread(
                                self._add_message_main,
                                f"[dim green]✓ Sections {selected} selected[/dim green]"
                            )
                        else:
                            self.call_from_thread(
                                self._add_message_main,
                                "[dim]✓ Using all sections[/dim]"
                            )
                        return selected if selected else None
                    except (json.JSONDecodeError, OSError):
                        time.sleep(0.1)
            time.sleep(0.5)
            waited += 0.5

        self.call_from_thread(
            self._add_message_main,
            "[dim yellow]⏱ Timed out — using all sections[/dim yellow]"
        )
        return None

    ## ── compose & mount ───────────────────────────────────────────

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
            Input(placeholder="Ask anything... (type / for commands)", id="query"),
            id="input-container"
        )
        yield OptionList(
            Option("/web       — Enable web search",              id="web"),
            Option("/local     — Switch to local mode",           id="local"),
            Option("/models    — Select AI model",                id="models"),
            Option("/new       — Start new chat",                 id="new"),
            Option("/history   — Show past chats",                id="history"),
            Option("/links     — Set number of sites to search",  id="links"),
            Option("/feed      — Set content feed size per chunk", id="feed"),
            Option("/clear     — Clear screen",                   id="clear"),
            Option("/exit      — Exit LocalMind",                 id="exit"),
            id="command-menu"
        )
        yield OptionList(id="model-menu")
        yield Footer()

    def on_mount(self):
        self.query_one("#query").focus()
        threading.Thread(target=self._load_models, daemon=True).start()
        self._launch_section_viewer()  ## still fine, called from main thread at startup

    ## ── model loading ─────────────────────────────────────────────

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
            f"● {mode}  |  model: {self.current_model}  |  feed: {self.feed_size}w  |  "
            f"session: {self.session_id}  |  ctrl+s stop  |  ctrl+c quit"
        )

    ## ── model menu ────────────────────────────────────────────────

    def _show_model_menu(self):
        self._showing_model_menu = True
        menu = self.query_one("#model-menu", OptionList)
        menu.clear_options()
        if not self.installed_models:
            self._add_message_main("[bold red]No models found. Run: ollama pull mistral[/bold red]")
            self._showing_model_menu = False
            return
        for m in self.installed_models:
            prefix = "● " if m["name"] == self.current_model else "  "
            display = (
                f"{prefix}{m['name']}  —  "
                f"{m['param']} · {m['quant']} · {m['size_gb']}GB · ~{m['ram_needed']}GB RAM"
            )
            menu.add_option(Option(display, id=f"model__{m['name']}"))
        menu.add_option(Option("  ── cancel ──", id="model__cancel"))
        self.query_one("#command-menu", OptionList).remove_class("visible")
        menu.add_class("visible")
        menu.focus()

    ## ── message helpers ───────────────────────────────────────────

    def _add_message_main(self, text, markup=True):
        with self._msg_id_lock:
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

    ## ── input changed ─────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed):
        if self._showing_model_menu or self._setting_feed:
            return
        cmd_menu   = self.query_one("#command-menu", OptionList)
        model_menu = self.query_one("#model-menu", OptionList)
        model_menu.remove_class("visible")
        if event.value == "/":
            cmd_menu.add_class("visible")
            cmd_menu.focus()
        else:
            cmd_menu.remove_class("visible")

    ## ── option selected ───────────────────────────────────────────

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        option_id = event.option.id

        ## model menu
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
                        f"[dim]  {m['param']} · {m['quant']} · {m['size_gb']}GB"
                        f" · needs ~{m['ram_needed']}GB RAM[/dim]"
                    )
                    break
            return

        ## command menu — close it first
        self.query_one("#command-menu", OptionList).remove_class("visible")

        if option_id == "web":
            self.query_one("#query").value = ""
            self.query_one("#query").focus()
            self.web_search = True
            self._update_status()
            self._add_message_main("[bold green]✓ Web search enabled[/bold green]")

        elif option_id == "local":
            self.query_one("#query").value = ""
            self.query_one("#query").focus()
            self.web_search = False
            self._update_status()
            self._add_message_main("[bold yellow]✓ Local mode enabled[/bold yellow]")

        elif option_id == "models":
            self.query_one("#query").value = ""
            self._show_model_menu()

        elif option_id == "new":
            self.query_one("#query").value = ""
            self.query_one("#query").focus()
            self.session_id = new_session()
            self._update_status()
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            scroll.remove_children()
            scroll.mount(Static(
                f"[bold cyan]LocalMind[/bold cyan] [dim]— new chat started ({self.session_id})[/dim]",
                classes="message", markup=True
            ))

        elif option_id == "history":
            self.query_one("#query").value = ""
            self.query_one("#query").focus()
            sessions = list_sessions()
            if not sessions:
                self._add_message_main("[dim]No previous chats found[/dim]")
            else:
                history_text = "\n[bold blue]Past Chats:[/bold blue]\n"
                for s in sessions[:5]:
                    history_text += f"  [cyan]{s['_id']}[/cyan] — {str(s['first_message'])[:50]}\n"
                self._add_message_main(history_text)

        elif option_id == "links":
            self.query_one("#query").value = ""
            self.query_one("#query").focus()
            self._add_message_main(
                "[bold yellow]Type /links 3 or /links 5 to set number of sites (1–10)[/bold yellow]"
            )

        elif option_id == "feed":
            ## FIX: don't clear input — let user type number directly
            self._setting_feed = True
            self.query_one("#query").value = ""
            self.query_one("#query").placeholder = f"Enter feed size (current: {self.feed_size}) e.g. 3000..."
            self.query_one("#query").focus()
            self._add_message_main(
                f"[bold yellow]Feed size controls words per chunk fed to the model.\n"
                f"  Current: {self.feed_size} words\n"
                f"  Suggested: 1500 (fast)  3000 (balanced)  6000 (detailed)  10000 (max)\n"
                f"  Type a number and press Enter:[/bold yellow]"
            )

        elif option_id == "clear":
            self.query_one("#query").value = ""
            self.query_one("#query").focus()
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            scroll.remove_children()
            scroll.mount(Static(
                "[bold cyan]LocalMind[/bold cyan] [dim]— chat cleared[/dim]",
                classes="message", markup=True
            ))

        elif option_id == "exit":
            self.exit()

    ## ── actions ───────────────────────────────────────────────────

    def action_hide_menu(self):
        if self._setting_feed:
            self._setting_feed = False
            self.query_one("#query").placeholder = "Ask anything... (type / for commands)"
        self._showing_model_menu = False
        self.query_one("#command-menu", OptionList).remove_class("visible")
        self.query_one("#model-menu", OptionList).remove_class("visible")
        self.query_one("#query").value = ""
        self.query_one("#query").focus()

    def action_stop(self):
        if self.is_generating:
            self._stop_event.set()
            self._add_message_main("[bold red]⏹ Stopping...[/bold red]")

    ## ── input submitted ───────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted):
        if self.is_generating:
            return

        query = event.value.strip()
        if not query:
            return

        ## FIX: feed size setting mode
        if self._setting_feed:
            self._setting_feed = False
            self.query_one("#query").placeholder = "Ask anything... (type / for commands)"
            self.query_one("#query").value = ""
            try:
                n = int(query)
                if 500 <= n <= 10000:
                    self.feed_size = n
                    self._update_status()
                    self._add_message_main(
                        f"[bold green]✓ Feed size set to {n} words per chunk[/bold green]"
                    )
                else:
                    self._add_message_main(
                        "[bold red]Feed size must be between 500 and 10000[/bold red]"
                    )
            except ValueError:
                self._add_message_main("[bold red]Please enter a number e.g. 3000[/bold red]")
            return

        if query == "/":
            return

        self.query_one("#query").value = ""

        ## /links inline command
        if query.startswith("/links "):
            try:
                n = int(query.split(" ")[1])
                if 1 <= n <= 10:
                    self.max_links = n
                    self._update_status()
                    self._add_message_main(f"[bold green]✓ Will search top {n} sites[/bold green]")
                else:
                    self._add_message_main("[bold red]Please enter a number between 1 and 10[/bold red]")
            except:
                self._add_message_main("[bold red]Usage: /links 3[/bold red]")
            return

        ## /feed inline command (typed directly without menu)
        if query.startswith("/feed "):
            try:
                n = int(query.split(" ")[1])
                if 500 <= n <= 10000:
                    self.feed_size = n
                    self._update_status()
                    self._add_message_main(f"[bold green]✓ Feed size set to {n} words per chunk[/bold green]")
                else:
                    self._add_message_main("[bold red]Feed size must be between 500 and 10000[/bold red]")
            except:
                self._add_message_main("[bold red]Usage: /feed 3000[/bold red]")
            return

        self._add_message_main(f"[bold white]You:[/bold white] {query}")

        if self.web_search:
            threading.Thread(target=self.run_search, args=(query,), daemon=True).start()
        else:
            threading.Thread(target=self.run_local, args=(query,), daemon=True).start()

    ## ── run search ────────────────────────────────────────────────

    def run_search(self, query):
        save_message(self.session_id, "user", query)
        self.is_generating = True
        self._stop_event.clear()
        self._last_web_answer = ""
        total_start = time.time()

        def progress(msg):
            self.call_from_thread(self._add_message_main, msg)

        def chunk_callback(action, data):
            if self._stop_event.is_set():
                return None
            if action == "start":
                result_holder = {}
                done_event = threading.Event()

                def do_add():
                    result_holder["id"] = self._add_message_main(data)
                    done_event.set()

                self.call_from_thread(do_add)
                done_event.wait(timeout=2)
                return result_holder.get("id")
            elif action == "token":
                self.call_from_thread(self._update_message, data["id"], data["text"])
                self._last_web_answer = data["text"]
            return None

        sources = ask_localmind(
            query,
            max_links=self.max_links,
            feed_size=self.feed_size,
            progress_callback=progress,
            chunk_callback=chunk_callback,
            stop_flag=self._stop_event.is_set,
            model=self.current_model,
            section_picker_callback=self._section_picker
        )

        if self._last_web_answer:
            save_message(self.session_id, "assistant", self._last_web_answer)

        total_elapsed = round(time.time() - total_start, 1)
        self.call_from_thread(
            self._add_message_main,
            f"[dim]⏱ Total: {total_elapsed}s (search + scrape + generation)[/dim]"
        )

        if sources:
            src_text = "\n[bold blue]Sources:[/bold blue]\n"
            seen  = set()
            count = 1
            for i in range(0, len(sources), 2):
                url   = sources[i+1] if i+1 < len(sources) else ""
                title = sources[i]
                if url not in seen:
                    seen.add(url)
                    src_text += f"  [cyan]{count}.[/cyan] {title} [dim]{url}[/dim]\n"
                    count += 1
            self.call_from_thread(self._add_message_main, src_text)

        self.is_generating = False

    ## ── run local ─────────────────────────────────────────────────

    def run_local(self, query):
        history = build_context(self.session_id)
        save_message(self.session_id, "user", query)
        self.is_generating = True
        self._stop_event.clear()
        start = time.time()

        self.call_from_thread(
            self._add_message_main,
            f"[dim cyan]🤖 Thinking with {self.current_model}...[/dim cyan]"
        )

        ## get msg_id synchronously via Event bridge
        msg_id_holder = {}
        done_event = threading.Event()

        def do_add():
            msg_id_holder["id"] = self._add_message_main("[bold cyan]LocalMind:[/bold cyan] ")
            done_event.set()

        self.call_from_thread(do_add)
        done_event.wait(timeout=2)
        msg_id = msg_id_holder.get("id")

        full_prompt = build_local_prompt(query, history, self.current_model)

        model_lower = self.current_model.lower()
        if "tinyllama" in model_lower or ":1b" in model_lower:
            ctx_limit = 2048
            max_pred  = 256
        elif any(x in model_lower for x in ["3b", "phi", "gemma"]):
            ctx_limit = 4096
            max_pred  = 512
        else:
            ctx_limit = 8192
            max_pred  = 512

        answer = ""

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": self.current_model,
                    "prompt": full_prompt,
                    "stream": True,
                    "keep_alive": -1,
                    "options": {
                        "num_predict": max_pred,
                        "temperature": 0.3,
                        "num_ctx": ctx_limit
                    }
                },
                stream=True,
                timeout=120
            )

            for line in response.iter_lines():
                if self._stop_event.is_set():
                    response.close()
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
            if not self._stop_event.is_set():
                self.call_from_thread(
                    self._add_message_main,
                    f"[bold red]Error: {e}[/bold red]"
                )

        if answer:
            save_message(self.session_id, "assistant", answer)

        elapsed = round(time.time() - start, 1)
        self.call_from_thread(self._add_message_main, f"[dim]⏱ {elapsed}s[/dim]")
        self.is_generating = False


if __name__ == "__main__":
    app = LocalMind()
    app.run()