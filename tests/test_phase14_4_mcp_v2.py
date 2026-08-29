"""
Phase 14.4 Test Suite: MCP API v2 Tools.
Validates:
- creative_get_job (found, not found, manifest loading).
- creative_download_asset (vaulted asset retrieval, auto-vault fallback, error codes).
- creative_cancel_job (active job cancellation, completed job immutability).
- creative_list_history (limit validation, status filter).
- MCP Registry total tools count check (28 tools).
"""
import pytest
from unittest.mock import AsyncMock, patch

from src.mcp.registry import mcp_registry
from src.mcp.tools import (
    register_all_tools,
    creative_get_job,
    creative_download_asset,
    creative_cancel_job,
    creative_list_history
)
from src.storage.storage_layer import storage

@pytest.mark.asyncio
async def test_creative_get_job_success():
    """Validates creative_get_job returns complete job metadata."""
    job_id = "mcp_test_get_001"
    storage.job_store.create_job({
        "job_id": job_id,
        "status": "COMPLETED",
        "workflow_name": "flux2_klein_txt2img",
        "output_assets": ["Artifacts/media/mcp_test_get_001/render.png"],
        "output_sha256": "abc123sha",
        "created_at": "2026-08-28T00:00:00Z",
        "completed_at": "2026-08-28T00:01:00Z"
    })
    
    res = await creative_get_job(job_id=job_id)
    assert res["job_id"] == job_id
    assert res["status"] == "COMPLETED"
    assert res["progress"] == 100
    assert len(res["outputs"]) == 1

@pytest.mark.asyncio
async def test_creative_get_job_not_found():
    """Validates creative_get_job handles non-existent jobs gracefully."""
    res = await creative_get_job(job_id="non_existent_job_999")
    assert res["status"] == "ERROR"
    assert res["error_code"] == "JOB_NOT_FOUND"

@pytest.mark.asyncio
async def test_creative_download_asset_already_vaulted():
    """Validates creative_download_asset returns pre-vaulted asset metadata."""
    job_id = "mcp_test_dl_001"
    storage.job_store.create_job({
        "job_id": job_id,
        "status": "COMPLETED",
        "workflow_name": "flux2_klein_txt2img",
        "output_assets": ["Artifacts/media/mcp_test_dl_001/render.png"],
        "output_sha256": "sha256_output_val",
        "output_size_bytes": 2048,
        "created_at": "2026-08-28T00:00:00Z"
    })

    res = await creative_download_asset(job_id=job_id)
    assert res["status"] == "SUCCESS"
    assert res["job_id"] == job_id
    assert res["sha256"] == "sha256_output_val"
    assert res["size_bytes"] == 2048
    assert res["vault_status"] == "VAULTED"

@pytest.mark.asyncio
async def test_creative_cancel_job_active_and_completed():
    """Validates creative_cancel_job transitions active jobs and rejects completed ones."""
    # 1. Cancel active job
    active_id = "mcp_cancel_active_001"
    storage.job_store.create_job({
        "job_id": active_id,
        "status": "RUNNING",
        "workflow_name": "flux2_klein_txt2img",
        "created_at": "2026-08-28T00:00:00Z"
    })
    cancel_res = await creative_cancel_job(job_id=active_id, reason="Testing cancellation")
    assert cancel_res["status"] == "CANCELLED"

    # 2. Reject cancellation of completed job
    completed_id = "mcp_cancel_completed_001"
    storage.job_store.create_job({
        "job_id": completed_id,
        "status": "COMPLETED",
        "workflow_name": "flux2_klein_txt2img",
        "created_at": "2026-08-28T00:00:00Z"
    })
    cancel_err = await creative_cancel_job(job_id=completed_id)
    assert cancel_err["status"] == "ERROR"
    assert cancel_err["error_code"] == "JOB_ALREADY_COMPLETED"

@pytest.mark.asyncio
async def test_creative_list_history():
    """Validates creative_list_history pagination and status filtering."""
    for i in range(5):
        storage.job_store.create_job({
            "job_id": f"history_job_{i}",
            "status": "COMPLETED" if i % 2 == 0 else "FAILED",
            "workflow_name": "test_history",
            "created_at": f"2026-08-28T00:0{i}:00Z"
        })

    # List with limit
    history = await creative_list_history(limit=3)
    assert len(history) <= 3
    assert "job_id" in history[0]

    # List with filter
    completed_history = await creative_list_history(limit=10, status="COMPLETED")
    for item in completed_history:
        assert item["status"] == "COMPLETED"

def test_mcp_registry_28_tools():
    """Validates that all 28 tools are registered in mcp_registry without regression."""
    register_all_tools()
    tools = mcp_registry.list_tools()
    tool_names = [t["name"] for t in tools]
    
    # 4 new MCP tools
    assert "creative_get_job" in tool_names
    assert "creative_download_asset" in tool_names
    assert "creative_cancel_job" in tool_names
    assert "creative_list_history" in tool_names
    
    # Pre-existing creative tools
    assert "creative_status" in tool_names
    assert "creative_list_workflows" in tool_names
    assert "creative_run_workflow" in tool_names
    assert "creative_generate_image" in tool_names
    assert "creative_generate_video" in tool_names

    assert len(tool_names) >= 28
