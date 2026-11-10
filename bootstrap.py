## File Name: bootstrap.py
## Description: One-click installer + launcher for LocalMind.
##              Uses ONLY the Python standard library so it can run on a
##              fresh machine. It will:
##                1. create a private virtual environment (.venv)
##                2. install the Python dependencies into it
##                3. install Ollama if it is missing
##                4. start the Ollama server if it is not running
##                5. download a default model if none is installed
##                6. launch LocalMind
##              Safe to run again and again — finished steps are skipped.
## Path: bootstrap.py

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT          = os.path.dirname(os.path.abspath(__file__))
VENV_DIR      = os.path.join(ROOT, ".venv")
REQUIREMENTS  = os.path.join(ROOT, "requirements.txt")
STAMP_FILE    = os.path.join(VENV_DIR, ".requirements.sha256")
OLLAMA_URL    = os.environ.get("OLLAMA_HOST_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("LOCALMIND_MODEL", "llama3.2:3b")
IS_WIN        = os.name == "nt"
IS_MAC        = sys.platform == "darwin"


## ── pretty output ────────────────────────────────────────────────

if IS_WIN:
    os.system("")  ## enables ANSI colours in Windows consoles

def step(msg):  print(f"\n\033[1;36m==> {msg}\033[0m", flush=True)
def ok(msg):    print(f"    \033[32m✔ {msg}\033[0m", flush=True)
def warn(msg):  print(f"    \033[33m! {msg}\033[0m", flush=True)
def fail(msg):
    print(f"\n\033[1;31m✘ {msg}\033[0m\n", flush=True)
    sys.exit(1)


## ── 1 + 2: virtual environment and Python packages ───────────────

def venv_python():
    if IS_WIN:
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python")


def ensure_venv():
    step("Checking Python environment")
    if sys.version_info < (3, 10):
        fail(f"Python 3.10+ is required (found {sys.version.split()[0]}).")
    ok(f"Python {sys.version.split()[0]}")

    py = venv_python()
    if not os.path.exists(py):
        print("    creating virtual environment in .venv ...", flush=True)
        try:
            subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
        except subprocess.CalledProcessError:
            hint = ("sudo apt install python3-venv" if sys.platform.startswith("linux")
                    else "reinstall Python with the 'venv' option")
            fail(f"Could not create a virtual environment. Try: {hint}")
    ok("virtual environment ready")

    with open(REQUIREMENTS, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    try:
        with open(STAMP_FILE) as f:
            if f.read().strip() == digest:
                ok("Python packages already installed")
                return py
    except OSError:
        pass

    step("Installing Python packages (first run only, ~1-2 min)")
    subprocess.call([py, "-m", "pip", "install", "--upgrade", "pip", "-q"])
    if subprocess.call([py, "-m", "pip", "install", "-r", REQUIREMENTS]) != 0:
        fail("pip install failed — check your internet connection and run again.")
    with open(STAMP_FILE, "w") as f:
        f.write(digest)
    ok("Python packages installed")
    return py


## ── 3: Ollama ────────────────────────────────────────────────────

def find_ollama():
    exe = shutil.which("ollama")
    if exe:
        return exe
    candidates = []
    if IS_WIN:
        local = os.environ.get("LOCALAPPDATA", "")
        candidates += [
            os.path.join(local, "Programs", "Ollama", "ollama.exe"),
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Ollama", "ollama.exe"),
        ]
    elif IS_MAC:
        candidates += ["/usr/local/bin/ollama", "/opt/homebrew/bin/ollama",
                       "/Applications/Ollama.app/Contents/Resources/ollama"]
    else:
        candidates += ["/usr/local/bin/ollama", "/usr/bin/ollama"]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def download(url, dest):
    print(f"    downloading {url}", flush=True)
    with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r    {done * 100 // total:3d}%  ({done >> 20} / {total >> 20} MB)",
                      end="", flush=True)
    print(flush=True)


def install_ollama():
    step("Installing Ollama (local AI engine)")
    if IS_WIN:
        if shutil.which("winget"):
            subprocess.call(["winget", "install", "-e", "--id", "Ollama.Ollama",
                             "--silent", "--accept-package-agreements",
                             "--accept-source-agreements"])
        if not find_ollama():
            setup = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
            download("https://ollama.com/download/OllamaSetup.exe", setup)
            subprocess.call([setup, "/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"])
    elif IS_MAC:
        if shutil.which("brew"):
            subprocess.call(["brew", "install", "ollama"])
        else:
            fail("Please install Ollama from https://ollama.com/download "
                 "(drag it to Applications), then run this again.")
    else:
        if not shutil.which("curl"):
            fail("curl is required to install Ollama: sudo apt install curl")
        print("    (you may be asked for your password)", flush=True)
        subprocess.call(["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"])

    exe = find_ollama()
    if not exe:
        fail("Ollama installation failed. Install it manually from "
             "https://ollama.com/download and run this again.")
    ok("Ollama installed")
    return exe


## ── 4: Ollama server ─────────────────────────────────────────────

def ollama_api(path, timeout=3):
    with urllib.request.urlopen(OLLAMA_URL + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def server_running():
    try:
        ollama_api("/api/tags")
        return True
    except Exception:
        return False


def ensure_server(exe):
    step("Starting Ollama server")
    if server_running():
        ok("Ollama server is running")
        return
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "stdin": subprocess.DEVNULL}
    if IS_WIN:
        kwargs["creationflags"] = 0x00000008 | 0x00000200  ## DETACHED | NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([exe, "serve"], **kwargs)
    for _ in range(60):
        if server_running():
            ok("Ollama server is running")
            return
        time.sleep(1)
    fail("Ollama server did not start. Try running 'ollama serve' manually.")


## ── 5: model ─────────────────────────────────────────────────────

def ensure_model(exe):
    step("Checking AI models")
    try:
        models = [m["name"] for m in ollama_api("/api/tags").get("models", [])]
    except Exception:
        models = []
    if models:
        ok("installed: " + ", ".join(models))
        return
    print(f"    no model found — downloading '{DEFAULT_MODEL}' (~2 GB, first run only)",
          flush=True)
    if subprocess.call([exe, "pull", DEFAULT_MODEL]) != 0:
        fail(f"Could not download model '{DEFAULT_MODEL}'. Check your internet and run again.")
    ok(f"model '{DEFAULT_MODEL}' ready")


## ── 6: launch ────────────────────────────────────────────────────

def main():
    os.chdir(ROOT)
    print("\033[1;32m")
    print("  ╦  ┌─┐┌─┐┌─┐┬  ╔╦╗┬┌┐┌┌┬┐")
    print("  ║  │ ││  ├─┤│  ║║║││││ ││")
    print("  ╩═╝└─┘└─┘┴ ┴┴─┘╩ ╩┴┘└┘─┴┘   one-click setup")
    print("\033[0m", flush=True)

    py  = ensure_venv()
    exe = find_ollama() or install_ollama()
    ok(f"Ollama found: {exe}")
    ensure_server(exe)
    ensure_model(exe)

    step("Launching LocalMind")
    if "--setup-only" in sys.argv:
        ok("setup complete")
        return
    sys.exit(subprocess.call([py, os.path.join(ROOT, "localmind.py")]))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(130)
