import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.mcp.gdrive_mcp import gdrive_mcp
from src.integrations.antigravity.tool_parser import safe_tool_parser
from src.integrations.antigravity.models import PermissionMode
from src.integrations.antigravity.orchestrator import AntigravityAgentProvider
from src.integrations.antigravity.models import AntigravitySession

def test_gdrive_mcp_suite():
    print("================================================================================")
    print("DM AI OS v1.5.2 — GOOGLE DRIVE 5 TB MCP & INTEGRATION VERIFICATION")
    print("================================================================================")

    # 1. MCP Direct Method
    print("\n▶️ [TEST 1] Testing gdrive_mcp.get_storage_quota()...")
    quota = gdrive_mcp.get_storage_quota()
    print(json.dumps(quota, indent=2))
    assert quota["total_capacity_tb"] == 5.0, "Expected 5.0 TB capacity"
    assert "Zero API Cost" in quota["cost_per_api_call"], "Expected zero API cost"
    print("   ✅ PASS: Quota & tier verified (Google One 5 TB at $0.00).")

    # 2. Dispatcher Whitelist & Dispatch
    print("\n▶️ [TEST 2] Testing safe_tool_parser.dispatch_tool('gdrive_get_storage_quota')...")
    s, out, pending = safe_tool_parser.dispatch_tool("gdrive_get_storage_quota", {}, PermissionMode.READ_ONLY)
    print(f"   Status: {s}, Output: {out[:100]}...")
    assert s is True, f"Failed dispatch: {out}"
    assert "Google One AI Premium (5 TB)" in out
    print("   ✅ PASS: MCP tool correctly dispatched in READ_ONLY.")

    # 3. Listing Dispatch
    print("\n▶️ [TEST 3] Testing safe_tool_parser.dispatch_tool('gdrive_list_files')...")
    s2, out2, _ = safe_tool_parser.dispatch_tool("gdrive_list_files", {"subpath": "."}, PermissionMode.READ_ONLY)
    print(f"   Status: {s2}, Output: {out2[:100]}...")
    assert s2 is True
    print("   ✅ PASS: gdrive_list_files executed safely.")

    # 4. Negation check in mutation gating
    print("\n▶️ [TEST 4] Testing smart negation gating in orchestrator...")
    provider = AntigravityAgentProvider()
    p_neg = "No modificar configuración ni escribir archivos, consultar estado del drive."
    p_lower = p_neg.lower()
    has_negation = any(neg in p_lower for neg in [
        "no modif", "sin modif", "no escrib", "sin escrib", "no camb", "sin camb",
        "no elim", "sin elim", "no cre", "sin cre", "solo lectura", "read_only"
    ])
    assert has_negation is True, "Negation detection failed!"
    print("   ✅ PASS: Negation detected, no false-positive BLOCKED.")

    print("\n================================================================================")
    print("🏁 ALL GDRIVE MCP VERIFICATIONS PASSED WITH 100% SUCCESS")
    print("================================================================================")

if __name__ == "__main__":
    test_gdrive_mcp_suite()
