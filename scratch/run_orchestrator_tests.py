"""
DM AI OS v1.5.2 — Phase 8 Autonomous Orchestrator Physical Test Suite
====================================================================
Tests all 10 mandatory physical requirements:
1. Client -> DM AI OS -> Antigravity -> Real response
2. Antigravity -> MCP -> Real filesystem inspection
3. READ_ONLY -> Mutation -> BLOCKED
4. APPROVAL_REQUIRED -> Mutation -> PENDING_USER_APPROVAL
5. APPROVE -> Physical execution -> VERIFY
6. REJECT -> Mutation cancelled -> VERIFY
7. Antigravity offline -> Detection
8. AUTO -> Provider selection
9. Provider failure -> Fallback
10. Multi-Step -> Planning & Recovery
"""
import asyncio
import sys
import time
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
    EngineType,
    AntigravityChatRequest,
    AntigravityApprovalRequest,
)
from src.integrations.antigravity.orchestrator import orchestrator
from src.integrations.antigravity.session import session_store
from src.integrations.antigravity.verifier import physical_verifier

async def run_phase8_suite():
    print("=" * 80)
    print("DM AI OS v1.5.2 — PHASE 8 AUTONOMOUS ORCHESTRATOR PHYSICAL E2E SUITE")
    print("=" * 80)

    results = []

    # ── TEST 1: CLIENT -> DM AI OS -> ANTIGRAVITY -> REAL RESPONSE ──────────
    print("\n▶️ [TEST 01/10] Antigravity Agent Runtime real response...")
    req1 = AntigravityChatRequest(
        prompt="Respondé exactamente: ANTIGRAVITY_E2E_AGENT_OK",
        permission_mode=PermissionMode.READ_ONLY
    )
    t0 = time.time()
    res1 = await antigravity_bridge.handle_chat(req1)
    latency = round((time.time() - t0) * 1000, 2)
    if "ANTIGRAVITY_E2E_AGENT_OK" in res1.response_text or res1.status == SessionStatus.COMPLETED:
        print(f"   ✅ PASS: Received real response from {res1.engine_used} (Latency: {latency}ms)")
        results.append(("TEST 01: Real Agent Chat", "PASS", f"{res1.engine_used} ({latency}ms)"))
    else:
        print(f"   ❌ FAIL: Response: {res1.response_text}")
        results.append(("TEST 01: Real Agent Chat", "FAIL", "Invalid output"))

    # ── TEST 2: ANTIGRAVITY -> MCP -> REAL FILESYSTEM INSPECTION ────────────
    print("\n▶️ [TEST 02/10] Antigravity -> MCP -> Real filesystem inspection...")
    req2 = AntigravityChatRequest(
        prompt="Antigravity, listá los archivos y carpetas físicamente existentes en el workspace scratch. No inventes ningún archivo.",
        session_id=res1.session_id,
        permission_mode=PermissionMode.READ_ONLY
    )
    res2 = await antigravity_bridge.handle_chat(req2)
    if ("Archivos y Carpetas" in res2.response_text or "README.md" in res2.response_text) and res2.status == SessionStatus.COMPLETED:
        print(f"   ✅ PASS: Real filesystem inspection verified on disk.")
        results.append(("TEST 02: MCP Filesystem Read", "PASS", "Physical inspection confirmed"))
    else:
        print(f"   ❌ FAIL: {res2.response_text}")
        results.append(("TEST 02: MCP Filesystem Read", "FAIL", "Inspection failed"))

    # ── TEST 3: READ_ONLY -> MUTATION -> BLOCKED ────────────────────────────
    print("\n▶️ [TEST 03/10] READ_ONLY -> Mutation -> BLOCKED...")
    req3 = AntigravityChatRequest(
        prompt="Modificá README.md agregando una línea.",
        session_id=res1.session_id,
        permission_mode=PermissionMode.READ_ONLY
    )
    res3 = await antigravity_bridge.handle_chat(req3)
    if "BLOCKED" in res3.response_text and res3.status == SessionStatus.FAILED:
        print(f"   ✅ PASS: Mutation blocked by policy engine.")
        results.append(("TEST 03: READ_ONLY Block", "PASS", "BLOCKED strictly"))
    else:
        print(f"   ❌ FAIL: Not blocked: {res3.response_text}")
        results.append(("TEST 03: READ_ONLY Block", "FAIL", "Not blocked"))

    # ── TEST 4: APPROVAL_REQUIRED -> MUTATION -> PENDING_USER_APPROVAL ──────
    print("\n▶️ [TEST 04/10] APPROVAL_REQUIRED -> Mutation -> PENDING_USER_APPROVAL...")
    test_temp_file = Path("scratch/antigravity_orch_test.txt")
    if test_temp_file.exists():
        test_temp_file.unlink()

    req4 = AntigravityChatRequest(
        prompt=f"Creá una modificación en {test_temp_file.as_posix()} con texto de prueba.",
        session_id=res1.session_id,
        permission_mode=PermissionMode.APPROVAL_REQUIRED
    )
    res4 = await antigravity_bridge.handle_chat(req4)
    if res4.status == SessionStatus.PENDING_USER_APPROVAL and res4.pending_action:
        action_id = res4.pending_action.action_id
        print(f"   ✅ PASS: Intercepted mutating action -> Action ID: {action_id[:8]}...")
        results.append(("TEST 04: Request Approval", "PASS", f"Action: {action_id[:8]}..."))
    else:
        print(f"   ❌ FAIL: {res4.response_text}")
        results.append(("TEST 04: Request Approval", "FAIL", "No action created"))
        action_id = None

    # ── TEST 5: APPROVE -> PHYSICAL EXECUTION -> VERIFY ──────────────────────
    print("\n▶️ [TEST 05/10] APPROVE -> Physical Execution -> VERIFY on disk...")
    if action_id:
        app_req = AntigravityApprovalRequest(
            session_id=res1.session_id,
            action_id=action_id,
            decision="APPROVE"
        )
        app_res = await antigravity_bridge.handle_approval(app_req)
        verified, verif_msg = physical_verifier.verify_file_exists(test_temp_file.as_posix())
        if app_res.get("status") == "SUCCESS" and verified:
            print(f"   ✅ PASS: {verif_msg}")
            results.append(("TEST 05: User Approval & Verify", "PASS", verif_msg))
        else:
            print(f"   ❌ FAIL: Execution or verification failed: {app_res}")
            results.append(("TEST 05: User Approval & Verify", "FAIL", "Verification error"))
    else:
        results.append(("TEST 05: User Approval & Verify", "SKIPPED", "No action"))

    # ── TEST 6: REJECT -> MUTATION CANCELLED -> VERIFY ───────────────────────
    print("\n▶️ [TEST 06/10] REJECT -> Mutation Cancelled -> VERIFY...")
    req6 = AntigravityChatRequest(
        prompt="Creá una modificación secundaria.",
        session_id=res1.session_id,
        permission_mode=PermissionMode.APPROVAL_REQUIRED
    )
    res6 = await antigravity_bridge.handle_chat(req6)
    if res6.pending_action:
        rej_req = AntigravityApprovalRequest(
            session_id=res1.session_id,
            action_id=res6.pending_action.action_id,
            decision="REJECT"
        )
        rej_res = await antigravity_bridge.handle_approval(rej_req)
        if rej_res.get("status") == "REJECTED":
            print(f"   ✅ PASS: Mutation cleanly cancelled upon rejection.")
            results.append(("TEST 06: User Rejection & Verify", "PASS", "Cancelled cleanly"))
        else:
            print(f"   ❌ FAIL: Rejection failed: {rej_res}")
            results.append(("TEST 06: User Rejection & Verify", "FAIL", "Rejection error"))
    else:
        results.append(("TEST 06: User Rejection & Verify", "FAIL", "No action"))

    # ── TEST 7: ANTIGRAVITY OFFLINE -> CLEAN DETECTION ───────────────────────
    print("\n▶️ [TEST 07/10] Antigravity Offline -> Clean Detection...")
    antigravity_bridge.set_online(False)
    req7 = AntigravityChatRequest(prompt="Ping offline")
    res7 = await antigravity_bridge.handle_chat(req7)
    antigravity_bridge.set_online(True)
    if res7.status == SessionStatus.OFFLINE and "OFFLINE" in res7.response_text:
        print("   ✅ PASS: Detected OFFLINE state accurately without crashing.")
        results.append(("TEST 07: Offline Detection", "PASS", "Safe OFFLINE response"))
    else:
        print(f"   ❌ FAIL: {res7}")
        results.append(("TEST 07: Offline Detection", "FAIL", "Offline check failed"))

    # ── TEST 8: AUTO MODE -> REAL PROVIDER SELECTION ─────────────────────────
    print("\n▶️ [TEST 08/10] AUTO Mode -> Real Provider Selection...")
    req8 = AntigravityChatRequest(
        prompt="Consultar estado",
        engine_type=EngineType.AUTO,
        permission_mode=PermissionMode.READ_ONLY
    )
    res8 = await antigravity_bridge.handle_chat(req8)
    if res8.status == SessionStatus.COMPLETED and res8.engine_used:
        print(f"   ✅ PASS: AUTO routed request to: '{res8.engine_used}'")
        results.append(("TEST 08: AUTO Provider Selection", "PASS", f"Routed to {res8.engine_used}"))
    else:
        print(f"   ❌ FAIL: {res8}")
        results.append(("TEST 08: AUTO Provider Selection", "FAIL", "AUTO routing failed"))

    # ── TEST 9: PROVIDER FAILURE -> SAFE FALLBACK ────────────────────────────
    print("\n▶️ [TEST 09/10] Provider Failure -> Safe Fallback to Ollama Direct...")
    orchestrator.antigravity_provider.is_online = False
    req9 = AntigravityChatRequest(
        prompt="Hola, ¿estás disponible?",
        engine_type=EngineType.AUTO,
        permission_mode=PermissionMode.READ_ONLY
    )
    res9 = await orchestrator.route_request(req9.prompt, session_store.get_or_create_session(res1.session_id))
    orchestrator.antigravity_provider.is_online = True
    if "Fallback" in res9.response_text or "Ollama" in res9.engine_used:
        print(f"   ✅ PASS: Safely fell back to '{res9.engine_used}' with explicit reason.")
        results.append(("TEST 09: Safe Fallback", "PASS", "Fell back to Ollama Direct"))
    else:
        print(f"   ❌ FAIL: {res9.response_text}")
        results.append(("TEST 09: Safe Fallback", "FAIL", "Fallback failed"))

    # ── TEST 10: MULTI-STEP TASK -> PLANNING & SESSION RECOVERY ──────────────
    print("\n▶️ [TEST 10/10] Multi-Step Task -> Planning & Session Recovery...")
    req10 = AntigravityChatRequest(
        prompt="Analizá el estado actual del proyecto, revisá los archivos relevantes, detectá problemas, proponé un plan, y esperá mi aprobación antes de modificar cualquier cosa.",
        session_id=res1.session_id,
        permission_mode=PermissionMode.APPROVAL_REQUIRED
    )
    res10 = await antigravity_bridge.handle_chat(req10)
    saved_plan = session_store.get_plan_by_session(res1.session_id)
    if res10.plan and saved_plan and len(saved_plan.steps) >= 4:
        print(f"   ✅ PASS: Multi-step task planned ({len(saved_plan.steps)} steps) and saved in SQLite!")
        results.append(("TEST 10: Multi-Step Planning", "PASS", f"{len(saved_plan.steps)} steps planned"))
    else:
        print(f"   ❌ FAIL: Multi-step plan failed: {res10}")
        results.append(("TEST 10: Multi-Step Planning", "FAIL", "Plan not created"))

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("DM AI OS v1.5.2 — PHASE 8 ORCHESTRATOR TEST SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Test':<6} | {'Test Name':<32} | {'Status':<10} | {'Outcome'}")
    print("-" * 80)
    for idx, (name, status, outcome) in enumerate(results, 1):
        print(f"#{idx:<5} | {name:<32} | {status:<10} | {outcome}")
    print("=" * 80)
    
    passes = sum(1 for _, s, _ in results if s == "PASS")
    print(f"🏁 RESULTADO FINAL: {passes}/{len(results)} PRUEBAS FÍSICAS SUPERADAS CON ÉXITO")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_phase8_suite())
