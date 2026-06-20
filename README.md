# LocalMind

**A privacy-first AI research assistant with dual-terminal human-in-the-loop control.**

LocalMind runs an Ollama language model entirely on your own machine and pairs it with a supervised web research pipeline — every search query, link, and scraped section is approved by you before the model ever sees it.

---

## 🚀 Quick Start (5 minutes)

```bash
# 1. Install Ollama and pull a model
ollama pull mistral

# 2. Install MongoDB and make sure it's running
mongod --version

# 3. Clone the repo and install Python dependencies
git clone https://github.com/Im-Lokesh-R/localmind.git
cd localmind
pip install -r requirements.txt

# 4. Run it
python localmind.py
```

Two terminal windows will open — the main chat window and the control panel (used only when web search mode is on). Type `/web` to enable web search, or just start chatting in local mode.

---

## 🖥 Run `localmind` from anywhere (optional, Windows)

Instead of typing the full Python command every time, you can set up a global `localmind` command:

1. Open **Command Prompt as Administrator**
2. Run:

```bash
echo @echo off > C:\Windows\localmind.bat
echo python "C:\path\to\your\localmind\localmind.py" >> C:\Windows\localmind.bat
```

Replace `C:\path\to\your\localmind\` with wherever you cloned the repo.

3. Open a **new** Command Prompt anywhere and type:

```bash
localmind
```

It launches instantly from any folder. ✅

---

## 📋 Requirements

| Requirement | Details |
|---|---|
| Python | 3.10 or later |
| Ollama | Installed and running, exposing API on `localhost:11434` |
| MongoDB | Installed and running on `localhost:27017` |
| RAM | 4GB+ for small models (TinyLlama/Phi3), more for larger models |
| Terminal | Capable of running two simultaneous terminal windows |

---

## 📦 Installation (Detailed)

### Step 1 — Install Ollama

Download from [ollama.com/download](https://ollama.com/download) and install.

Pull at least one model:

```bash
ollama pull mistral        # 7B, balanced quality and speed
ollama pull phi3            # 3.8B, faster, good quality
ollama pull tinyllama       # 1B, fastest, lower quality
```

### Step 2 — Install MongoDB

Download from [mongodb.com/try/download/community](https://www.mongodb.com/try/download/community).

During setup, make sure **"Install MongoDB as a Service"** is checked so it starts automatically.

Verify it's running:

```bash
mongod --version
```

### Step 3 — Clone and install Python dependencies

```bash
git clone https://github.com/Im-Lokesh-R/localmind.git
cd localmind
pip install -r requirements.txt
```

### Step 4 — Run LocalMind

```bash
python localmind.py
```

This launches the main chat terminal. It will automatically open a second terminal — the **control panel** — used only when web search mode is active.

---

## 🎮 Usage

### Local chat mode (default)

Just type your question and press Enter. The active Ollama model answers directly, with conversation memory carried across the session.

### Web search mode

Type `/web` to enable it. From here, every query goes through a 4-step human-supervised pipeline:

1. **Query selection** — pick from 3 AI-rewritten versions of your question
2. **Link selection** — choose which search results to scrape
3. **Content selection** — choose which scraped link(s) the model is allowed to read
4. **Generation** — the model answers using only what you approved

All of this happens in the **control panel** window (Terminal 2), which opens automatically.

### Commands

| Command | Description |
|---|---|
| `/web` | Enable web search mode |
| `/local` | Switch back to local-only mode |
| `/models` | List installed Ollama models and switch between them |
| `/panel` | Reopen the control panel if it was closed |
| `/new` | Start a new chat session |
| `/history` | Show your 5 most recent past sessions |
| `/links 3` | Set how many search results to fetch per query (1–10) |
| `/feed 3000` | Set how many words are fed to the model per chunk (500–10,000) |
| `/clear` | Clear the current screen |
| `/exit` | Exit LocalMind |
| `Ctrl+S` | Stop generation immediately |
| `Ctrl+C` | Quit the application |

---

## 🏗 Architecture

```
Terminal 1 (localmind.py)          Terminal 2 (control_panel.py)
────────────────────────           ──────────────────────────────
Chat interface                     Human-in-the-loop research panel
Model selector                     Query / link / content selection
Session memory (MongoDB)           Activated only in web search mode
        │                                    │
        └──────── panel_bridge.py ───────────┘
              (file-based IPC, heartbeat monitored)
```

| File | Role |
|---|---|
| `localmind.py` | Entry point — chat interface, commands, model selector |
| `scripts/control_panel.py` | Entry point — control panel UI (Terminal 2) |
| `scripts/pipeline.py` | Query rewriting, search, scraping, generation logic |
| `scripts/panel_bridge.py` | File-based IPC between the two terminals |
| `scripts/memory.py` | MongoDB session and message storage |
| `scripts/router.py` | RSS feed routing and relevance scoring |
| `scripts/search.py` | DuckDuckGo, Wikipedia, and arXiv search integrations |
| `scripts/scraper.py` | Web page scraping and content extraction |

---

## ⚠️ Troubleshooting

**"No Ollama models found"** — Make sure Ollama is installed and running (`ollama list` should show at least one model).

**Control panel doesn't open** — Type `/panel` in the main window to relaunch it manually.

**MongoDB connection error** — Make sure MongoDB is running as a service. Check with `mongod --version` and that the MongoDB service is started in Windows Services.

**Slow responses** — Try a smaller model with `/models` (Phi3 or TinyLlama), or lower the feed size with `/feed 1500`.

---

## 📄 License

Academic project — NasoTech Pvt Ltd internship program, 2026.