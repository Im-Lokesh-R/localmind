## File Name: memory.py
## Description: Chat memory using MongoDB (falls back to a local JSON file
##              when MongoDB is not installed / not running, so the app
##              always starts — handy for demos)
## Path: scripts/memory.py
## Created By: Tharun     Created On: 2026-06-02

## Import - Libraries
import json
import os
import threading
from datetime import datetime

MONGO_URI = os.environ.get("LOCALMIND_MONGO_URI", "mongodb://localhost:27017/")
DATA_DIR  = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
JSON_FILE = os.path.join(DATA_DIR, "chats.json")

chats   = None
BACKEND = "json"

## try MongoDB first (short timeout so startup isn't blocked)
try:
    from pymongo import MongoClient
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
    client.admin.command("ping")
    db      = client["localmind"]
    chats   = db["chats"]
    BACKEND = "mongodb"
except Exception:
    chats = None

_lock = threading.Lock()


def _load_json():
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_json(rows):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = JSON_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    os.replace(tmp, JSON_FILE)


def save_message(session_id, role, content):
    ## save a single message
    if chats is not None:
        chats.insert_one({
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now()
        })
        return
    with _lock:
        rows = _load_json()
        rows.append({
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        _save_json(rows)


def get_history(session_id, last_n=5):
    ## get last N messages for context
    if chats is not None:
        messages = list(chats.find(
            {"session_id": session_id},
            {"_id": 0, "role": 1, "content": 1}
        ).sort("timestamp", -1).limit(last_n))
        messages.reverse()
        return messages
    with _lock:
        rows = [r for r in _load_json() if r.get("session_id") == session_id]
    rows.sort(key=lambda r: r.get("timestamp", ""))
    return [{"role": r["role"], "content": r["content"]} for r in rows[-last_n:]]


def build_context(session_id):
    ## build conversation context string for the LLM
    messages = get_history(session_id)
    if not messages:
        return ""
    context = "Previous conversation:\n"
    for m in messages:
        prefix = "User" if m["role"] == "user" else "LocalMind"
        context += f"{prefix}: {m['content'][:200]}\n"
    return context


def new_session():
    ## generate a new unique session ID
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def list_sessions():
    ## get all unique session IDs with their first message
    if chats is not None:
        sessions = chats.aggregate([
            {"$sort": {"timestamp": 1}},
            {"$group": {
                "_id": "$session_id",
                "first_message": {"$first": "$content"},
                "started": {"$first": "$timestamp"}
            }},
            {"$sort": {"started": -1}}
        ])
        return list(sessions)
    with _lock:
        rows = _load_json()
    rows.sort(key=lambda r: r.get("timestamp", ""))
    first = {}
    for r in rows:
        sid = r.get("session_id")
        if sid not in first:
            first[sid] = {"_id": sid, "first_message": r.get("content", ""),
                          "started": r.get("timestamp", "")}
    return sorted(first.values(), key=lambda s: s["started"], reverse=True)
