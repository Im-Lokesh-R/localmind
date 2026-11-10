#!/usr/bin/env bash
# LocalMind - one-click setup and launch for macOS / Linux
# Run:  ./start.sh   (or double-click start.command on macOS)
set -e
cd "$(dirname "$0")"

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done

if [ -z "$PY" ]; then
  echo "==> Python 3.10+ not found - installing ..."
  if [ "$(uname)" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then brew install python@3.12; PY=python3.12
    else echo "Install Python from https://www.python.org/downloads/ and run again."; exit 1; fi
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip curl; PY=python3
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip curl; PY=python3
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --noconfirm python python-pip curl; PY=python3
  else
    echo "Please install Python 3.10+ and run again."; exit 1
  fi
fi

# Debian/Ubuntu ship python without venv by default
if ! "$PY" -c 'import venv, ensurepip' 2>/dev/null && command -v apt-get >/dev/null 2>&1; then
  sudo apt-get install -y python3-venv
fi

exec "$PY" bootstrap.py "$@"
