## File Name: panel_bridge.py
## Description: Shared communication bridge between LocalMind and Control Panel
## Path: scripts/panel_bridge.py
## Created By: Lokesh R     Created On: 2026-06-16

import json
import os
import time
import tempfile

## all temp files in one place
BRIDGE_DIR    = tempfile.gettempdir()
STATE_FILE    = os.path.join(BRIDGE_DIR, "lm_state.json")
TRIGGER_FILE  = os.path.join(BRIDGE_DIR, "lm_trigger.txt")
RESULT_FILE   = os.path.join(BRIDGE_DIR, "lm_result.json")
READY_FILE    = os.path.join(BRIDGE_DIR, "lm_panel_ready.txt")
HEARTBEAT_FILE = os.path.join(BRIDGE_DIR, "lm_heartbeat.txt")

## step names — used as state["step"] values
STEP_IDLE          = "idle"
STEP_QUERY_SELECT  = "query_select"
STEP_LINK_SELECT   = "link_select"
STEP_SECTION_SELECT = "section_select"
STEP_GENERATING    = "generating"
STEP_DONE          = "done"
STEP_ERROR         = "error"

def write_state(step, data, instruction="", meta=None):
    ## terminal 1 writes this to tell panel what to show
    payload = {
        "step":        step,
        "data":        data,        ## list of items to show
        "instruction": instruction, ## tailored instruction for this step
        "meta":        meta or {},  ## extra info (site name, counts etc)
        "timestamp":   time.time()
    }
    ## write atomically — write to temp then rename to avoid partial reads
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)

    ## touch trigger so panel knows to re-read
    with open(TRIGGER_FILE, "w") as f:
        f.write(str(time.time()))

def read_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def write_result(result):
    ## panel writes this after user makes selection
    payload = {
        "result":    result,   ## whatever user selected
        "timestamp": time.time()
    }
    tmp = RESULT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, RESULT_FILE)

def read_result():
    try:
        with open(RESULT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def clear_result():
    if os.path.exists(RESULT_FILE):
        try:
            os.remove(RESULT_FILE)
        except:
            pass

def get_trigger_mtime():
    try:
        return os.path.getmtime(TRIGGER_FILE)
    except:
        return None

def is_panel_ready():
    return os.path.exists(READY_FILE)

def panel_heartbeat():
    ## panel writes this every second to show it is alive
    with open(HEARTBEAT_FILE, "w") as f:
        f.write(str(time.time()))

def is_panel_alive(max_age=5):
    ## terminal 1 checks this — if heartbeat older than 5s, panel is dead
    try:
        mtime = os.path.getmtime(HEARTBEAT_FILE)
        return (time.time() - mtime) < max_age
    except:
        return False

def clean_all():
    for f in [STATE_FILE, TRIGGER_FILE, RESULT_FILE, READY_FILE, HEARTBEAT_FILE]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except:
                pass

def prepare_for_result():
    ## call this BEFORE write_state so result is cleared before user sees the step
    ## not inside wait_for_result which is called AFTER user may have already answered
    clear_result()

def wait_for_result(timeout=120, stop_flag=None, poll=0.3):
    ## FIX: do NOT clear result here — it should already be cleared via prepare_for_result
    ## clearing here was deleting results that arrived before wait_for_result was called
    waited = 0
    while waited < timeout:
        if stop_flag and stop_flag():
            return None
        result = read_result()
        if result is not None:
            return result["result"]
        time.sleep(poll)
        waited += poll
    return None