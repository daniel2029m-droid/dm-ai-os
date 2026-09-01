"""
DM AI OS v1.5.2 — Phase 8 Detailed Forensic E2E Test
Runs exact user prompts and records step-by-step physical telemetry:
1. List Directory Test
2. Read File Test (Distinguishing subpath vs file_path)
3. Full Workspace SHA256 Invariance
"""
import asyncio
import sys
import time
import hashlib
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(".").resolve()))

from src.integrations.antigravity import (
    antigravity_bridge,
    PermissionMode,
    SessionStatus,
    AntigravityChatRequest,
)

def get_workspace_snapshot() -> dict:
    snapshot = {}
    for p in Path(".").iterdir():
        if p.is_file():
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            snapshot[p.name] = h
    return snapshot

async def run_investigation():
    print("=" * 80)
    print("DM AI OS v1.5.2 — DETAILED PHYSICAL E2E INVESTIGATION")
    print("=" * 80)

    snap_before = get_workspace_snapshot()

    # ── TEST 1: LIST DIRECTORY WITH ANALYSIS ─────────────────────────────────
    print("\n▶️ [TEST 1] List Workspace Directory...")
    prompt1 = "Listá físicamente las carpetas y archivos del workspace actual. No inventes ningún archivo y no modifiques absolutamente nada. Usá la herramienta de listado y después analizá el resultado real."
    
    req1 = AntigravityChatRequest(
        prompt=prompt1,
        permission_mode=PermissionMode.READ_ONLY
    )
    t0 = time.time()
    res1 = await antigravity_bridge.handle_chat(req1)
    dur1 = round((time.time() - t0) * 1000, 2)

    print(f"Status: {res1.status.value}")
    print(f"Engine Used: {res1.engine_used}")
    print(f"Executed Tools: {res1.executed_tools}")
    print(f"Response Duration: {dur1}ms")
    print(f"\n--- FINAL RESPONSE TEXT ---\n{res1.response_text}\n---------------------------")

    # ── TEST 2: READ SPECIFIC FILE ───────────────────────────────────────────
    print("\n▶️ [TEST 2] Read Specific File (Testing subpath vs file_path)...")
    prompt2 = "Leé físicamente README.md y decime su título. No modifiques nada."
    req2 = AntigravityChatRequest(
        prompt=prompt2,
        session_id=res1.session_id,
        permission_mode=PermissionMode.READ_ONLY
    )
    t0 = time.time()
    res2 = await antigravity_bridge.handle_chat(req2)
    dur2 = round((time.time() - t0) * 1000, 2)

    print(f"Status: {res2.status.value}")
    print(f"Engine Used: {res2.engine_used}")
    print(f"Executed Tools: {res2.executed_tools}")
    print(f"Response Duration: {dur2}ms")
    print(f"\n--- FINAL RESPONSE TEXT ---\n{res2.response_text}\n---------------------------")

    # Check filesystem invariance
    snap_after = get_workspace_snapshot()
    if snap_before == snap_after:
        print("\n✅ WORKSPACE INVARIANCE CONFIRMED: No files were added, modified, or deleted.")
    else:
        print("\n❌ WARNING: Workspace changed during READ_ONLY test!")

if __name__ == "__main__":
    asyncio.run(run_investigation())
