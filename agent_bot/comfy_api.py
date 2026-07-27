import asyncio
import json
import os
import logging
from pathlib import Path
import httpx

log = logging.getLogger("comfy_api")
AUTH_STATE = Path(r"C:\AgentScreenshots\recordings\auth_state.json")
BASE_URL   = "https://cloud.comfy.org"

# ── FORMATO INTERFAZ (UI_WORKFLOW_GROK) ───────────────────────────────────────
UI_WORKFLOW_GROK = {
  "last_node_id": 6,
  "last_link_id": 6,
  "nodes": [
    {"id": 2, "type": "SaveVideo", "pos": [-520, -680], "size": [630, 938], "inputs": [{"name": "video", "type": "VIDEO", "link": 1}], "widgets_values": ["video/Grok", "auto", "auto"]},
    {"id": 3, "type": "LoadImage", "pos": [-1270, -680], "size": [283, 340], "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": [2]}], "widgets_values": ["image.png", "image"]},
    {"id": 1, "type": "GrokVideoNode", "pos": [-960, -680], "size": [410, 400], "inputs": [{"name": "image", "type": "IMAGE", "link": 2}], "outputs": [{"name": "VIDEO", "type": "VIDEO", "links": [1]}], "widgets_values": ["grok-imagine-video-beta", "PROMPT_HERE", "720p", "auto", 6, 880926991, "randomize"]}
  ],
  "links": [[1, 1, 0, 2, 0, "VIDEO"], [2, 3, 0, 1, 0, "IMAGE"]],
  "extra": {"ds": {"scale": 0.54, "offset": [1752, 914]}},
  "version": 0.4
}

# ── FORMATO API ───────────────────────────────────────────────────────────────
def build_grok_workflow(image_filename, prompt):
    return {
        "3": {"class_type": "LoadImage", "inputs": {"image": image_filename, "upload": "image"}},
        "1": {"class_type": "GrokVideoNode", "inputs": {"image": ["3", 0], "model": "grok-imagine-video-beta", "prompt": prompt, "resolution": "720p", "seed": 880926991, "control_after_generate": "randomize"}},
        "2": {"class_type": "SaveVideo", "inputs": {"video": ["1", 0], "filename_prefix": "video/Grok", "format": "auto", "codec": "auto"}}
    }

def _get_auth_data():
    if not AUTH_STATE.exists(): return {}, ""
    with open(AUTH_STATE, encoding="utf-8") as f:
        data = json.load(f)
    cookies = {c["name"]: c["value"] for c in data.get("cookies", [])}
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    return cookies, ua

async def run_grok(image_path, prompt, batch_count=1):
    cookies, ua = _get_auth_data()
    headers = {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://cloud.comfy.org",
        "Referer": "https://cloud.comfy.org/",
        # Intentamos añadir X-Requested-With para evitar el 403
        "X-Requested-With": "XMLHttpRequest"
    }

    try:
        async with httpx.AsyncClient(base_url=BASE_URL, cookies=cookies, headers=headers) as client:
            with open(image_path, "rb") as f:
                r = await client.post("/upload/image", files={"image": (os.path.basename(image_path), f, "image/png")}, timeout=60)
            
            if r.status_code != 200:
                _log_api(f"Error 403 o similar: {r.status_code}. Pasando a modo UI...")
                return {"status": "error", "message": f"API bloqueada ({r.status_code})"}
            
            img_name = r.json().get("name")
            pids = []
            for i in range(batch_count):
                wf = build_grok_workflow(img_name, prompt)
                r = await client.post("/api/prompt", json={"prompt": wf, "client_id": "valeria-bot"}, timeout=30)
                if r.status_code in (200, 201):
                    pids.append(r.json().get("prompt_id"))
            
            return {"status": "success", "message": f"API OK: {len(pids)} tareas."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def _log_api(msg):
    with open("C:\\AgentScreenshots\\automation_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[API] {msg}\n")
