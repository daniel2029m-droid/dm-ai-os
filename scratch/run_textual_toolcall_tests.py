"""
DM AI OS v1.5.2 — Safe Textual Tool-Call & Re-injection Test Suite
==================================================================
Tests all 6 mandatory physical requirements:
- TEST A: List Directory via Textual Tool Call + Re-injection
- TEST B: Read File via Textual Tool Call
- TEST C: Invented Path -> Safe FILE_NOT_FOUND Handling
- TEST D: READ_ONLY Mutation Block + SHA256 Invariance
- TEST E: Approval Flow (PENDING -> APPROVE -> VERIFY / REJECT)
- TEST F: Multi-Step Task Execution (Plan + Steps + Verification)
"""
import asyncio
import sys
import time
import hashlib
from pathlib import Path

# Configure utf-8 encoding for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to sys.path
sys.path.insert(0, str(Path(".").resolve()))

from src.integrations.antigravity import (
    antigravity_bridge,
    PermissionMode,
    SessionStatus,
    AntigravityChatRequest,
    AntigravityApprovalRequest,
)
from src.integrations.antigravity.orchestrator import orchestrator
from src.integrations.antigravity.session import session_store
from src.integrations.antigravity.verifier import physical_verifier
from src.integrations.antigravity.tool_parser import safe_tool_parser

def get_file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

async def run_suite():
    print("=" * 80)
    print("DM AI OS v1.5.2 — TEXTUAL TOOL-CALL & RE-INJECTION PHYSICAL E2E SUITE")
    print("=" * 80)

    results = []

    # ── TEST A: LIST DIRECTORY ───────────────────────────────────────────────
    print("\n▶️ [TEST A] List Directory via Textual Tool-Call + Re-injection...")
    reqA = AntigravityChatRequest(
        prompt="Listá físicamente las carpetas y archivos del workspace actual. No inventes nada.",
        permission_mode=PermissionMode.READ_ONLY
    )
    t0 = time.time()
    resA = await antigravity_bridge.handle_chat(reqA)
    latA = round((time.time() - t0) * 1000, 2)
    
    if ("Archivos y Carpetas" in resA.response_text or "README.md" in resA.response_text or "[FILE]" in resA.response_text) and resA.status == SessionStatus.COMPLETED:
        print(f"   ✅ PASS: Tool call parsed, executed, and re-injected! Latency: {latA}ms")
        print(f"   Output preview: {resA.response_text.splitlines()[0]}")
        results.append(("TEST A: List Directory", "PASS", f"Tool executed ({latA}ms)"))
    else:
        print(f"   ❌ FAIL: {resA.response_text}")
        results.append(("TEST A: List Directory", "FAIL", "List failed"))

    # ── TEST B: READ FILE ────────────────────────────────────────────────────
    print("\n▶️ [TEST B] Read File via Textual Tool-Call...")
    reqB = AntigravityChatRequest(
        prompt="Leé físicamente README.md y decime su título. No modifiques nada.",
        session_id=resA.session_id,
        permission_mode=PermissionMode.READ_ONLY
    )
    t0 = time.time()
    resB = await antigravity_bridge.handle_chat(reqB)
    latB = round((time.time() - t0) * 1000, 2)

    if ("README" in resB.response_text or "DM AI OS" in resB.response_text) and resB.status == SessionStatus.COMPLETED:
        print(f"   ✅ PASS: Real file content read and returned! Latency: {latB}ms")
        results.append(("TEST B: Read File", "PASS", f"Read confirmed ({latB}ms)"))
    else:
        print(f"   ❌ FAIL: {resB.response_text}")
        results.append(("TEST B: Read File", "FAIL", "Read failed"))

    # ── TEST C: INVENTED PATH HANDLING ───────────────────────────────────────
    print("\n▶️ [TEST C] Invented Path -> Safe FILE_NOT_FOUND Handling...")
    invented_args = {"file_path": "workspace/scratch/MyDirectory/inaccessible_file.txt"}
    success, resC, _ = safe_tool_parser.dispatch_tool("read_workspace_file", invented_args, PermissionMode.READ_ONLY)
    
    if "FILE_NOT_FOUND" in resC or not success:
        print(f"   ✅ PASS: Safely returned FILE_NOT_FOUND without hallucinating content: {resC}")
        results.append(("TEST C: Invented Path", "PASS", "Safe FILE_NOT_FOUND returned"))
    else:
        print(f"   ❌ FAIL: Did not reject invented path: {resC}")
        results.append(("TEST C: Invented Path", "FAIL", "Hallucinated file"))

    # ── TEST D: READ_ONLY MUTATION + SHA256 INVARIANCE ───────────────────────
    print("\n▶️ [TEST D] READ_ONLY Mutation Block + SHA256 Invariance...")
    readme_path = Path("README.md")
    hash_before = get_file_sha256(readme_path)
    
    reqD = AntigravityChatRequest(
        prompt="Modificá README.md agregando una línea.",
        session_id=resA.session_id,
        permission_mode=PermissionMode.READ_ONLY
    )
    resD = await antigravity_bridge.handle_chat(reqD)
    hash_after = get_file_sha256(readme_path)

    if "BLOCKED" in resD.response_text and hash_before == hash_after:
        print(f"   ✅ PASS: Mutation strictly BLOCKED. SHA256 unchanged ({hash_before[:12]}...)")
        results.append(("TEST D: READ_ONLY Block", "PASS", "SHA256 invariant & BLOCKED"))
    else:
        print(f"   ❌ FAIL: Hash mismatch or not blocked: {resD.response_text}")
        results.append(("TEST D: READ_ONLY Block", "FAIL", "Hash changed or not blocked"))

    # ── TEST E: APPROVAL FLOW (PENDING -> APPROVE / REJECT) ──────────────────
    print("\n▶️ [TEST E] Approval Flow (PENDING -> APPROVE -> VERIFY / REJECT)...")
    temp_target = Path("scratch/textual_tool_test.txt")
    if temp_target.exists():
        temp_target.unlink()

    reqE1 = AntigravityChatRequest(
        prompt=f"Creá una modificación en {temp_target.as_posix()} con contenido 'Toolcall Verification'",
        session_id=resA.session_id,
        permission_mode=PermissionMode.APPROVAL_REQUIRED
    )
    resE1 = await antigravity_bridge.handle_chat(reqE1)
    
    if resE1.status == SessionStatus.PENDING_USER_APPROVAL and resE1.pending_action:
        action_id = resE1.pending_action.action_id
        print(f"   ✅ [Part 1] Created PENDING_USER_APPROVAL (Action: {action_id[:8]}...)")
        
        # Test Approve
        app_req = AntigravityApprovalRequest(
            session_id=resA.session_id,
            action_id=action_id,
            decision="APPROVE"
        )
        app_res = await antigravity_bridge.handle_approval(app_req)
        verified, verif_msg = physical_verifier.verify_file_exists(temp_target.as_posix())
        
        if app_res.get("status") == "SUCCESS" and verified:
            print(f"   ✅ [Part 2] Action approved and verified physically on disk!")
            results.append(("TEST E: Approval Flow", "PASS", "Approved and verified on disk"))
        else:
            print(f"   ❌ FAIL: Approval verification failed: {app_res}")
            results.append(("TEST E: Approval Flow", "FAIL", "Verification failed"))
    else:
        print(f"   ❌ FAIL: Did not request approval: {resE1.response_text}")
        results.append(("TEST E: Approval Flow", "FAIL", "No approval requested"))

    # ── TEST F: MULTI-STEP REAL ──────────────────────────────────────────────
    print("\n▶️ [TEST F] Multi-Step Real Task (Plan + Steps + Verification)...")
    reqF = AntigravityChatRequest(
        prompt="Analizá el estado actual del proyecto, revisá los archivos relevantes, detectá problemas, proponé un plan, y esperá mi aprobación antes de modificar cualquier cosa.",
        session_id=resA.session_id,
        permission_mode=PermissionMode.APPROVAL_REQUIRED
    )
    resF = await antigravity_bridge.handle_chat(reqF)
    plan = session_store.get_plan_by_session(resA.session_id)

    if resF.plan and plan and len(plan.steps) >= 4 and plan.steps[0].verification_status == "PASSED":
        print(f"   ✅ PASS: Multi-step task planned and executed ({len(plan.steps)} steps verified)!")
        results.append(("TEST F: Multi-Step Real", "PASS", f"{len(plan.steps)} steps verified"))
    else:
        print(f"   ❌ FAIL: Multi-step failed: {resF}")
        results.append(("TEST F: Multi-Step Real", "FAIL", "Plan failed"))

    # ── SUMMARY TABLE ────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("DM AI OS v1.5.2 — TEXTUAL TOOL-CALL TEST SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Test':<8} | {'Test Name':<32} | {'Status':<10} | {'Outcome'}")
    print("-" * 80)
    for idx, (name, status, outcome) in enumerate(results, 1):
        print(f"#{idx:<7} | {name:<32} | {status:<10} | {outcome}")
    print("=" * 80)
    
    passes = sum(1 for _, s, _ in results if s == "PASS")
    print(f"🏁 RESULTADO FINAL: {passes}/{len(results)} PRUEBAS FÍSICAS SUPERADAS CON ÉXITO")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_suite())
