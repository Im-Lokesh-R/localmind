## File Name: section_viewer.py
## Description: Persistent section viewer — stays open, handles multiple scrapes
## Path: scripts/section_viewer.py
## Created By: Lokesh R     Created On: 2026-06-16
## Updated By: Lokesh R     Updated On: 2026-06-16
## Fixed: no stale data on start, trigger file pattern, clean waiting screen

import json
import sys
import os
import time

POLL_INTERVAL = 0.3

def clear_screen():
    os.system("cls")

def show_waiting():
    clear_screen()
    print("\n" + "="*60)
    print("  🧠  LocalMind — Section Viewer")
    print("="*60)
    print("\n  Waiting for content to be scraped...")
    print("  This window will update automatically.")
    print("  Keep it open while using LocalMind.\n")
    print("="*60)

def show_sections(page_title, sections):
    clear_screen()
    print("\n" + "="*60)
    print(f"  📄  {page_title[:55]}")
    print("="*60)
    for s in sections:
        print(f"\n  [{s['index']}] {s['title']} ({s['word_count']} words)")
        preview = s["content"][:100].replace("\n", " ")
        print(f"       {preview}...")
    print("\n" + "="*60)
    print("  Type section numbers to use (e.g. 1,3,5)")
    print("  Press Enter with nothing to use ALL sections")
    print("="*60)

def main():
    sections_file = sys.argv[1]
    result_file   = sys.argv[2]
    ready_file    = sys.argv[3]
    trigger_file  = sys.argv[4] if len(sys.argv) > 4 else sections_file + ".trigger"

    ## delete any stale files from previous sessions on startup
    for f in [sections_file, result_file, trigger_file]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except:
                pass

    ## signal that viewer is ready
    with open(ready_file, "w") as f:
        f.write("ready")

    show_waiting()

    last_trigger_mtime = None

    while True:
        ## watch trigger file — localmind writes this AFTER sections file is fully written
        try:
            trigger_mtime = os.path.getmtime(trigger_file)
        except FileNotFoundError:
            time.sleep(POLL_INTERVAL)
            continue

        if trigger_mtime == last_trigger_mtime:
            time.sleep(POLL_INTERVAL)
            continue

        ## new trigger arrived
        last_trigger_mtime = trigger_mtime

        ## clear previous result
        if os.path.exists(result_file):
            try:
                os.remove(result_file)
            except:
                pass

        ## read sections with retry for partial write safety
        data = None
        for _ in range(5):
            try:
                with open(sections_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                break
            except (json.JSONDecodeError, OSError):
                time.sleep(0.1)

        if not data:
            show_waiting()
            continue

        page_title = data.get("title", "Unknown")
        sections   = data.get("sections", [])

        if not sections:
            show_waiting()
            continue

        show_sections(page_title, sections)

        try:
            user_input = input("\n  Your selection: ").strip()
            if user_input:
                selected = [
                    int(x.strip())
                    for x in user_input.split(",")
                    if x.strip().isdigit()
                ]
            else:
                selected = []
        except (EOFError, KeyboardInterrupt):
            selected = []

        ## write result
        try:
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump({"selected": selected}, f)
        except OSError:
            pass

        show_waiting()

if __name__ == "__main__":
    main()