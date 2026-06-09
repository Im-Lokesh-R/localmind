## File Name: memory.py
## Description: Chat memory using MongoDB
## Path: scripts/memory.py
## Created By: Lokesh R     Created On: 2026-06-02

## Import - Libraries
from pymongo import MongoClient
from datetime import datetime

## connect to MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["localmind"]
chats = db["chats"]

def save_message(session_id, role, content):
    ## save a single message to MongoDB
    chats.insert_one({
        "session_id": session_id,
        "role": role,
        "content": content,
        "timestamp": datetime.now()
    })

def get_history(session_id, last_n=5):
    ## get last N messages for context
    messages = list(chats.find(
        {"session_id": session_id},
        {"_id": 0, "role": 1, "content": 1}
    ).sort("timestamp", -1).limit(last_n))
    messages.reverse()
    return messages

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