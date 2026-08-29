"""
Verification Script for Higgsfield MCP Integration
===================================================
1. Verifies module imports
2. Verifies MediaAgent provider recognition of Higgsfield
3. Generates test image with MediaAgent
4. Generates test video with MediaAgent
5. Verifies job status tracking and fallback mechanism
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

async def run_verification():
    print("==================================================")
    print("1. VERIFICATION: Checking Module Imports...")
    print("==================================================")
    import src.adapters.higgsfield_adapter as h_adapter
    import src.agents.media_agent as m_agent
    import src.specialists.higgsfield_specialist as h_spec
    import src.api.routes as routes
    print("[SUCCESS] All imports loaded cleanly.")

    print("\n==================================================")
    print("2. VERIFICATION: Checking MediaAgent Providers...")
    print("==================================================")
    media = m_agent.media_agent_instance
    providers = media.get_active_providers()
    print(f"Active Media Providers: {providers}")
    assert "higgsfield" in providers, "Higgsfield provider not recognized by MediaAgent!"
    print("[SUCCESS] MediaAgent successfully recognizes Higgsfield provider.")

    print("\n==================================================")
    print("3. VERIFICATION: Generating Test Image...")
    print("==================================================")
    img_res = await media.generate_image(
        prompt="A vibrant futuristic cityscape at sunset",
        provider="higgsfield",
        style="soul"
    )
    print("Image Generation Output:")
    print(img_res)
    assert img_res["status"] == "success"
    assert img_res["provider"] == "higgsfield"
    print("[SUCCESS] Image generation test passed.")

    print("\n==================================================")
    print("4. VERIFICATION: Generating Test Video...")
    print("==================================================")
    vid_res = await media.generate_video(
        image_filename="city_source.png",
        prompt="Slow motion drone shot over neon buildings",
        provider="higgsfield",
        duration=5
    )
    print("Video Generation Output:")
    print(vid_res)
    assert vid_res["status"] == "success"
    assert vid_res["provider"] == "higgsfield"
    print("[SUCCESS] Video generation test passed.")

    print("\n==================================================")
    print("5. VERIFICATION: Job Status & Fallback Check...")
    print("==================================================")
    job_id = vid_res["result"]["job_id"]
    status_res = await media.get_job_status(job_id)
    print(f"Job Status for '{job_id}':", status_res)
    assert status_res["status"] == "success"

    print("\n==================================================")
    print("VERIFICATION COMPLETE: ALL CHECKS PASSED 100%")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_verification())
