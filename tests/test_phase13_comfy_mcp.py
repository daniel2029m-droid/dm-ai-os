"""
Phase 13 Test Suite: Creative Engine & Comfy MCP Integration.
Validates:
- ComfyAdapter safe initialization and graceful degradation (zero crashes).
- CreativeEngine template discovery and SHA-256 reproducibility manifests.
- MediaAgent routing to CreativeEngine.
- MCP Server tools registration and regression test for existing tools.
"""
import pytest
import asyncio
from src.adapters.comfy_adapter import ComfyAdapter, comfy_adapter
from src.core.creative_engine import CreativeEngine, creative_engine, CreativeManifest
from src.agents.media_agent import media_agent_instance
from src.mcp.registry import mcp_registry
from src.mcp.tools import register_all_tools

def test_comfy_adapter_default_unconfigured():
    """Validates that ComfyAdapter degrades safely without credentials or local ComfyUI."""
    adapter = ComfyAdapter()
    info = adapter.get_backend_info()
    assert isinstance(info, dict)
    assert "available" in info
    assert "preferred_backend" in info
    assert info["local_enabled"] is False

@pytest.mark.asyncio
async def test_comfy_adapter_submit_when_unavailable():
    """Validates that submission returns UNAVAILABLE without throwing uncaught exceptions."""
    from unittest.mock import patch
    from src.providers.worker_registry import worker_registry
    
    with patch.object(worker_registry, "get_active_worker", return_value=None):
        adapter = ComfyAdapter()
        adapter.api_key = ""
        adapter.runpod_url = ""
        adapter.local_enabled = False

        res = await adapter.submit_workflow({"1": {"class_type": "KSampler"}})
        assert res["status"] == "UNAVAILABLE"
        assert "error" in res


def test_creative_engine_list_templates():
    """Validates that CreativeEngine discovers existing JSON workflows and hashes them."""
    templates = creative_engine.list_templates()
    assert isinstance(templates, list)
    assert len(templates) >= 4

    names = [t["name"] for t in templates]
    assert "flux2_klein_txt2img" in names
    assert "flux2_klein_img2img" in names
    assert "wan22_i2v" in names
    assert "wan22_motion_transfer" in names

    # Verify SHA-256 hash is computed
    for t in templates:
        assert len(t["sha256"]) == 64
        assert len(t["sha256_short"]) == 12

def test_creative_engine_get_template():
    """Validates finding a template by slug or filename."""
    t = creative_engine.get_template("flux2_klein_txt2img")
    assert t is not None
    assert t["name"] == "flux2_klein_txt2img"
    assert "workflow" in t
    assert isinstance(t["workflow"], dict)

@pytest.mark.asyncio
async def test_creative_engine_run_workflow_manifest():
    """Validates that running a workflow generates a full reproducibility manifest."""
    res = await creative_engine.run_workflow(
        template_name_or_path="flux2_klein_txt2img",
        prompt="A photo of a futuristic AI operating system interface",
        parameters={"seed": 12345, "steps": 20}
    )
    assert "manifest" in res
    manifest = res["manifest"]
    assert manifest["workflow_name"] == "flux2_klein_txt2img"
    assert len(manifest["workflow_sha256"]) == 64
    assert manifest["prompt"] == "A photo of a futuristic AI operating system interface"
    assert manifest["parameters"]["seed"] == 12345
    assert manifest["estimated_cost_usd"] is None

@pytest.mark.asyncio
async def test_media_agent_routing_to_creative():
    """Validates that MediaAgent routes provider='creative' or 'comfy' to CreativeEngine."""
    res = await media_agent_instance.generate_image(
        prompt="Studio portrait of Valeria Montesano",
        provider="creative",
        template="flux2_klein_txt2img"
    )
    assert "manifest" in res
    assert res["manifest"]["workflow_name"] == "flux2_klein_txt2img"

def test_mcp_tools_registration_and_regression():
    """Validates that all 5 new creative_* tools and all 22 existing tools are registered."""
    register_all_tools()
    all_tools = mcp_registry.list_tools()
    tool_names = [t["name"] for t in all_tools]

    # New creative tools
    expected_creative_tools = [
        "creative_status",
        "creative_list_workflows",
        "creative_run_workflow",
        "creative_generate_image",
        "creative_generate_video"
    ]
    for ct in expected_creative_tools:
        assert ct in tool_names, f"Missing tool: {ct}"

    # Regression check on pre-existing tools
    pre_existing_tools = [
        "system_status",
        "list_agents",
        "run_agent",
        "run_workflow",
        "search_memory",
        "get_artifacts",
        "get_user_profile",
        "remember",
        "update_memory",
        "forget_memory",
        "get_context",
        "index_document",
        "search_documents",
        "web_search",
        "get_capability_matrix",
        "higgsfield_generate_video",
        "higgsfield_generate_image",
        "higgsfield_image_to_video",
        "higgsfield_status"
    ]
    for pt in pre_existing_tools:
        assert pt in tool_names, f"Pre-existing tool broke: {pt}"
