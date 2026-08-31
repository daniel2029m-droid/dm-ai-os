import asyncio
import sys
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
from src.integrations.antigravity.session import session_store
from src.providers.provider_manager import provider_manager

async def run_suite():
    print("=" * 80)
    print("DM AI OS v1.5.2 — ANTIGRAVITY REMOTE BRIDGE PHYSICAL E2E SUITE")
    print("=" * 80)

    results = []

    # ── TEST 01: PING / PONG EXACT VERIFICATION ──────────────────────────────
    print("\n▶️ [TEST 01/10] Ping exact response verification...")
    req1 = AntigravityChatRequest(
        prompt="Antigravity, respondé exactamente: ANTIGRAVITY_REMOTE_BRIDGE_OK",
        permission_mode=PermissionMode.READ_ONLY
    )
    res1 = await antigravity_bridge.handle_chat(req1)
    if res1.response_text == "ANTIGRAVITY_REMOTE_BRIDGE_OK" and res1.status == SessionStatus.COMPLETED:
        print(f"   ✅ PASS: Received exact '{res1.response_text}' (Latency: {res1.latency_ms}ms)")
        results.append(("TEST 01: Ping Pong", "PASS", f"{res1.latency_ms}ms"))
    else:
        print(f"   ❌ FAIL: Unexpected response '{res1.response_text}'")
        results.append(("TEST 01: Ping Pong", "FAIL", "Invalid output"))

    # ── TEST 02: READ_ONLY INSPECT FILE ──────────────────────────────────────
    print("\n▶️ [TEST 02/10] READ_ONLY inspect README.md...")
    req2 = AntigravityChatRequest(
        prompt="Antigravity, inspeccioná el archivo README.md del proyecto y decime su título. No modifiques nada.",
        session_id=res1.session_id,
        permission_mode=PermissionMode.READ_ONLY
    )
    res2 = await antigravity_bridge.handle_chat(req2)
    if "README.md" in res2.response_text and res2.status == SessionStatus.COMPLETED:
        print(f"   ✅ PASS: Inspected workspace file without mutating (Latency: {res2.latency_ms}ms)")
        results.append(("TEST 02: Read File", "PASS", f"{res2.latency_ms}ms"))
    else:
        print(f"   ❌ FAIL: {res2.response_text}")
        results.append(("TEST 02: Read File", "FAIL", "Read failed"))

    # ── TEST 03: MUTATION IN READ_ONLY STRICTLY BLOCKED ─────────────────────
    print("\n▶️ [TEST 03/10] Mutation in READ_ONLY must be BLOCKED...")
    req3 = AntigravityChatRequest(
        prompt="Modificá README.md agregando una línea.",
        session_id=res1.session_id,
        permission_mode=PermissionMode.READ_ONLY
    )
    res3 = await antigravity_bridge.handle_chat(req3)
    if "BLOCKED" in res3.response_text and res3.status == SessionStatus.FAILED:
        print(f"   ✅ PASS: Mutation strictly blocked by policy engine: '{res3.response_text.splitlines()[0]}'")
        results.append(("TEST 03: Read-Only Block", "PASS", "BLOCKED strictly"))
    else:
        print(f"   ❌ FAIL: Mutation was not blocked: {res3.response_text}")
        results.append(("TEST 03: Read-Only Block", "FAIL", "Not blocked"))

    # ── TEST 04: MUTATION IN APPROVAL_REQUIRED CREATES PENDING ACTION ────────
    print("\n▶️ [TEST 04/10] Mutation in APPROVAL_REQUIRED requests approval...")
    test_temp_file = Path("scratch/antigravity_temp_test.txt")
    if test_temp_file.exists():
        test_temp_file.unlink()

    req4 = AntigravityChatRequest(
        prompt=f"Agregá una línea de prueba en {test_temp_file.as_posix()}",
        session_id=res1.session_id,
        permission_mode=PermissionMode.APPROVAL_REQUIRED
    )
    res4 = await antigravity_bridge.handle_chat(req4)
    if res4.status == SessionStatus.PENDING_USER_APPROVAL and res4.pending_action:
        action_id = res4.pending_action.action_id
        print(f"   ✅ PASS: Intercepted mutating tool. Action ID: {action_id}")
        results.append(("TEST 04: Request Approval", "PASS", f"Action: {action_id[:8]}..."))
    else:
        print(f"   ❌ FAIL: Approval was not requested: {res4.response_text}")
        results.append(("TEST 04: Request Approval", "FAIL", "No action created"))
        action_id = None

    # ── TEST 05 & 06: USER APPROVES ACTION -> PHYSICAL EXECUTION ─────────────
    print("\n▶️ [TEST 05/10] User approves action from remote terminal...")
    if action_id:
        app_req = AntigravityApprovalRequest(
            session_id=res1.session_id,
            action_id=action_id,
            decision="APPROVE"
        )
        app_res = await antigravity_bridge.handle_approval(app_req)
        if app_res.get("status") == "SUCCESS" and test_temp_file.exists():
            print(f"   ✅ PASS: Action approved and file created physically ({test_temp_file.name})")
            results.append(("TEST 05: User Approval", "PASS", "Physical execution verified"))
        else:
            print(f"   ❌ FAIL: Execution failed: {app_res}")
            results.append(("TEST 05: User Approval", "FAIL", "Execution error"))
    else:
        results.append(("TEST 05: User Approval", "SKIPPED", "No action"))

    # ── TEST 07: USER REJECTS ACTION ─────────────────────────────────────────
    print("\n▶️ [TEST 07/10] User rejects mutating action...")
    req7 = AntigravityChatRequest(
        prompt=f"Modificá otro archivo secundario.",
        session_id=res1.session_id,
        permission_mode=PermissionMode.APPROVAL_REQUIRED
    )
    res7 = await antigravity_bridge.handle_chat(req7)
    if res7.pending_action:
        rej_req = AntigravityApprovalRequest(
            session_id=res1.session_id,
            action_id=res7.pending_action.action_id,
            decision="REJECT"
        )
        rej_res = await antigravity_bridge.handle_approval(rej_req)
        if rej_res.get("status") == "REJECTED":
            print(f"   ✅ PASS: Mutation canceled cleanly upon rejection.")
            results.append(("TEST 07: User Rejection", "PASS", "Rejected cleanly"))
        else:
            print(f"   ❌ FAIL: Rejection failed: {rej_res}")
            results.append(("TEST 07: User Rejection", "FAIL", "Rejection error"))
    else:
        results.append(("TEST 07: User Rejection", "FAIL", "No action to reject"))

    # ── TEST 08: OFFLINE DETECTION ───────────────────────────────────────────
    print("\n▶️ [TEST 08/10] Offline status detection...")
    antigravity_bridge.set_online(False)
    req8 = AntigravityChatRequest(prompt="Hola Antigravity")
    res8 = await antigravity_bridge.handle_chat(req8)
    antigravity_bridge.set_online(True)
    if res8.status == SessionStatus.OFFLINE and "OFFLINE" in res8.response_text:
        print("   ✅ PASS: Detected OFFLINE state accurately without crashing platform.")
        results.append(("TEST 08: Offline Detection", "PASS", "Safe OFFLINE response"))
    else:
        print(f"   ❌ FAIL: Did not return offline status: {res8}")
        results.append(("TEST 08: Offline Detection", "FAIL", "Failed"))

    # ── TEST 09: SESSION PERSISTENCE (SQLITE) ────────────────────────────────
    print("\n▶️ [TEST 09/10] Session persistence in SQLite...")
    stored = session_store.get_or_create_session(session_id=res1.session_id)
    if len(stored.history) >= 2:
        print(f"   ✅ PASS: Recovered {len(stored.history)} history turns for session {res1.session_id[:8]}...")
        results.append(("TEST 09: SQLite Session", "PASS", f"{len(stored.history)} turns saved"))
    else:
        print(f"   ❌ FAIL: History not persisted: {stored.history}")
        results.append(("TEST 09: SQLite Session", "FAIL", "History missing"))

    # ── TEST 10: UNIFIED PROVIDER MANAGER INTEGRATION ────────────────────────
    print("\n▶️ [TEST 10/10] Unified ProviderManager route_chat integration...")
    prov_res = await provider_manager.route_chat(
        messages=[{"role": "user", "content": "Antigravity, respondé exactamente: ANTIGRAVITY_REMOTE_BRIDGE_OK"}],
        preferred_provider="antigravity"
    )
    if "ANTIGRAVITY_REMOTE_BRIDGE_OK" in prov_res["choices"][0]["message"]["content"]:
        print(f"   ✅ PASS: ProviderManager successfully routed to Antigravity Remote Bridge.")
        results.append(("TEST 10: ProviderManager E2E", "PASS", "HTTP route_chat OK"))
    else:
        print(f"   ❌ FAIL: Provider routing output: {prov_res}")
        results.append(("TEST 10: ProviderManager E2E", "FAIL", "Routing failed"))

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("DM AI OS v1.5.2 — ANTIGRAVITY REMOTE BRIDGE TEST SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Test':<6} | {'Test Name':<30} | {'Status':<10} | {'Outcome'}")
    print("-" * 80)
    for idx, (name, status, outcome) in enumerate(results, 1):
        print(f"#{idx:<5} | {name:<30} | {status:<10} | {outcome}")
    print("=" * 80)
    
    passes = sum(1 for _, s, _ in results if s == "PASS")
    print(f"🏁 RESULTADO FINAL: {passes}/{len(results)} PRUEBAS FÍSICAS SUPERADAS CON ÉXITO")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_suite())
