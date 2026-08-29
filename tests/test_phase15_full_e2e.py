"""
Phase 15 Full E2E Closed-Loop Integration Test Suite.
Validates the complete autonomous loop across all layers:
1. Phase 14 Creative Execution & Job Recording.
2. Ingestion of Performance Telemetry via MCP creative_record_metrics.
3. Creative Memory Pattern Extraction & Classification via creative_analyze_patterns.
4. Autonomous Strategy Brief Generation via creative_get_strategy_brief.
5. Brief Acceptance & Execution via StrategyEngine.execute_brief().
6. Auto-Vaulting of newly generated media and Manifest updates.
7. End-to-End Lineage & Verification via MCP creative_get_job and creative_download_asset.
"""
import pytest
import hashlib
from unittest.mock import AsyncMock, patch

from src.storage.storage_layer import storage
from src.core.creative_engine import creative_engine
from src.core.content_intelligence import content_intelligence
from src.core.creative_memory import creative_memory
from src.core.strategy_engine import strategy_engine
from src.mcp.tools import (
    register_all_tools,
    creative_run_workflow,
    creative_record_metrics,
    creative_analyze_patterns,
    creative_get_strategy_brief,
    creative_get_job,
    creative_download_asset
)

@pytest.mark.asyncio
async def test_full_phase15_autonomous_closed_loop():
    """Validates the full loop from telemetry to strategy to execution and auto-vaulting."""
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00fake_phase15_full_e2e_render"
    fake_sha256 = hashlib.sha256(fake_png).hexdigest()
    
    # ─── Step 1: Initial Phase 14 Generation ─────────────────────────────────
    with patch("src.adapters.comfy_adapter.comfy_adapter.submit_workflow", new=AsyncMock(return_value={
        "status": "SUBMITTED",
        "job_id": "cr_p15_init_001",
        "backend": "RUNPOD_COMFYUI"
    })):
        initial_job = await creative_run_workflow(
            template="flux2_klein_txt2img",
            prompt="A cinematic neon hero shot of a cybernetic warrior, centered composition, dramatic lighting",
            seed=7777
        )
        assert initial_job["status"] in ("SUBMITTED", "COMPLETED")
        j1_id = initial_job["job_id"]

    # ─── Step 2: Record Performance Telemetry via MCP ────────────────────────
    for i in range(3):
        m_res = await creative_record_metrics(
            job_id=j1_id,
            metrics={"channel": "facebook", "views": 1000, "likes": 120 + (i * 10), "retention_rate": 0.85, "ctr": 0.08}
        )
        assert m_res["status"] == "SUCCESS"

    # ─── Step 3: Refresh Creative Memory & Query via MCP ─────────────────────
    creative_memory.refresh_patterns()
    patterns = await creative_analyze_patterns(category="STYLE")
    assert isinstance(patterns, list)

    # ─── Step 4: Autonomous Strategy Synthesis via MCP ───────────────────────
    brief_res = await creative_get_strategy_brief(topic="advanced neural processor")
    assert brief_res["status"] == "SUCCESS"
    brief = brief_res["brief"]
    assert brief["status"] == "PROPOSED"
    assert "advanced neural processor" in brief["recommended_prompt"]
    brief_id = brief["brief_id"]

    # ─── Step 5: Accept & Execute Strategy Brief ─────────────────────────────
    strategy_engine.accept_brief(brief_id)
    
    with patch("src.adapters.comfy_adapter.comfy_adapter.submit_workflow", new=AsyncMock(return_value={
        "status": "SUBMITTED",
        "job_id": "cr_p15_dispatched_002",
        "backend": "RUNPOD_COMFYUI"
    })):
        with patch("src.adapters.comfy_adapter.comfy_adapter.get_job_outputs", new=AsyncMock(return_value=[
            {"filename": "neural_proc.png", "subfolder": "", "type": "output"}
        ])):
            with patch("src.adapters.comfy_adapter.comfy_adapter.download_output_bytes", new=AsyncMock(return_value=fake_png)):
                # Execute brief -> calls creative_engine.run_workflow
                executed_brief = await strategy_engine.execute_brief(brief_id)
                assert executed_brief["status"] == "DISPATCHED"
                dispatched_job_id = executed_brief["dispatched_job_id"]
                assert dispatched_job_id == "cr_p15_dispatched_002"

                # Auto-Vault the result
                vault_res = await creative_engine.download_and_vault_artifact(dispatched_job_id)
                assert vault_res["status"] == "COMPLETED"
                assert vault_res["output_sha256"] == fake_sha256

                # Verify via MCP creative_get_job
                job_info = await creative_get_job(job_id=dispatched_job_id)
                assert job_info["status"] == "COMPLETED"

                # Verify via MCP creative_download_asset
                dl_info = await creative_download_asset(job_id=dispatched_job_id)
                assert dl_info["status"] == "SUCCESS"
                assert dl_info["vault_status"] == "VAULTED"
                assert dl_info["sha256"] == fake_sha256
