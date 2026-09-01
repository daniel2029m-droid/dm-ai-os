import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.integrations.antigravity.creative_tools import creative_engine
from src.integrations.antigravity.tool_parser import safe_tool_parser
from src.integrations.antigravity.models import PermissionMode

def test_creative_suite():
    print("================================================================================")
    print("DM AI OS v1.5.2 — ANTIGRAVITY CREATIVE MULTIMODAL VERIFICATION SUITE")
    print("================================================================================")

    # 1. FaceSwap Engine Direct
    print("\n▶️ [TEST 1] Testing creative_engine.faceswap_image()...")
    res1 = creative_engine.faceswap_image(
        target_image="@Image 1",
        source_face="@Image 2",
        preserve_outfit=True,
        same_pose=True
    )
    print("   Output File:", res1["output_file"])
    print("   Download URL:", res1["download_url"])
    assert res1["status"] == "SUCCESS"
    assert Path(res1["output_file"]).exists(), "Deliverable image not found on disk!"
    assert "Descargar Imagen" in res1["preview_markdown"]
    print("   ✅ PASS: FaceSwap generated physical deliverable with preview & download links.")

    # 2. Animate Image Direct
    print("\n▶️ [TEST 2] Testing creative_engine.animate_image()...")
    res2 = creative_engine.animate_image(
        image_path="@Image 1",
        motion_prompt="Cinematic subtle motion, 4k 60fps",
        duration_seconds=5
    )
    print("   Output File:", res2["output_file"])
    print("   Download URL:", res2["download_url"])
    assert res2["status"] == "SUCCESS"
    assert Path(res2["output_file"]).exists(), "Deliverable video not found on disk!"
    assert "Descargar Video" in res2["preview_markdown"]
    print("   ✅ PASS: Animation generated physical video deliverable.")

    # 3. Tool Parser Dispatch for FaceSwap
    print("\n▶️ [TEST 3] Testing safe_tool_parser.dispatch_tool('faceswap_image')...")
    s, out, pending = safe_tool_parser.dispatch_tool(
        "faceswap_image",
        {"target_image": "@Image 1", "source_face": "@Image 2", "preserve_outfit": True, "same_pose": True},
        PermissionMode.READ_ONLY
    )
    print("   Status:", s)
    assert s is True
    assert "FaceSwap Generativo Completado" in out
    assert "Descargar Imagen" in out
    print("   ✅ PASS: FaceSwap tool parsed, executed, and returned markdown preview.")

    # 4. Tool Parser Dispatch for Animate Image
    print("\n▶️ [TEST 4] Testing safe_tool_parser.dispatch_tool('animate_image')...")
    s4, out4, _ = safe_tool_parser.dispatch_tool(
        "animate_image",
        {"image_path": "@Image 1", "motion_prompt": "Walk along beach", "duration_seconds": 5},
        PermissionMode.READ_ONLY
    )
    print("   Status:", s4)
    assert s4 is True
    assert "Animación de Video Generada" in out4
    assert "Descargar Video" in out4
    print("   ✅ PASS: Animate tool parsed, executed, and returned video preview.")

    print("\n================================================================================")
    print("🏁 ALL MULTIMODAL CREATIVE TOOLS VERIFIED WITH 100% SUCCESS")
    print("================================================================================")

if __name__ == "__main__":
    test_creative_suite()
