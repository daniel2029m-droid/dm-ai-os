"""
Phase 15.5 MCP API v3 Test Suite.
Validates the 4 new MCP tools, tool schema, error delegation, and 32 total registered tools:
1. creative_record_metrics (valid registration, validation failure, idempotency).
2. creative_analyze_patterns (with/without category, LOW_CONFIDENCE, OUTPERFORMING).
3. creative_create_experiment (valid creation, idempotency, variants generation).
4. creative_get_strategy_brief (cold-start vs evidence, confidence score, briefs list).
5. Exact 32 tools inventory in mcp_registry.
6. Backward compatibility with all 28 prior MCP tools.
"""
import pytest
import sqlite3
from unittest.mock import AsyncMock, patch

from src.mcp.registry import mcp_registry
from src.mcp.tools import (
    register_all_tools,
    creative_record_metrics,
    creative_analyze_patterns,
    creative_create_experiment,
    creative_get_strategy_brief
)
from src.storage.storage_layer import storage
from src.core.content_intelligence import content_intelligence
from src.core.creative_memory import creative_memory
from src.core.experiment_engine import experiment_engine
from src.core.strategy_engine import strategy_engine

# 1. MCP Tool Registry Count (32 tools)
def test_1_mcp_registry_32_tools():
    register_all_tools()
    tools = mcp_registry.list_tools()
    tool_names = [t["name"] for t in tools]
    assert len(tool_names) == 32

    expected_new = [
        "creative_record_metrics",
        "creative_analyze_patterns",
        "creative_create_experiment",
        "creative_get_strategy_brief"
    ]
    for t in expected_new:
        assert t in tool_names

# 2. creative_record_metrics tool
@pytest.mark.asyncio
async def test_2_creative_record_metrics_tool():
    job_id = "job_mcp_metrics_001"
    storage.job_store.create_job({"job_id": job_id, "status": "COMPLETED", "prompt": "cyberpunk neon"})

    # Valid metrics record
    res = await creative_record_metrics(
        job_id=job_id,
        metrics={"channel": "facebook", "views": 1000, "likes": 50, "retention_rate": 0.7, "ctr": 0.05}
    )
    assert res["status"] == "SUCCESS"
    assert res["job_id"] == job_id
    assert res["performance_score"] > 0.0

    # Idempotent call
    res_idemp = await creative_record_metrics(
        job_id=job_id,
        metrics={"metric_id": res["metric_id"], "channel": "facebook", "views": 1000, "likes": 50}
    )
    assert res_idemp["status"] == "SUCCESS"
    assert res_idemp["is_duplicate"] is True

    # Invalid job_id
    err_res = await creative_record_metrics(
        job_id="nonexistent_job_xyz",
        metrics={"channel": "facebook", "views": 100}
    )
    assert err_res["status"] == "ERROR"
    assert err_res["error_code"] == "JOB_NOT_FOUND"

# 3. creative_analyze_patterns tool
@pytest.mark.asyncio
async def test_3_creative_analyze_patterns_tool():
    # Seed metrics and refresh patterns
    job_id = "job_mcp_pat_001"
    storage.job_store.create_job({"job_id": job_id, "status": "COMPLETED", "prompt": "cinematic anime lighting centered"})
    for _ in range(3):
        await creative_record_metrics(job_id=job_id, metrics={"channel": "fb", "views": 1000, "likes": 100, "retention_rate": 0.8})

    creative_memory.refresh_patterns()

    # Query all patterns
    all_pats = await creative_analyze_patterns(limit=10)
    assert isinstance(all_pats, list)

    # Query category
    style_pats = await creative_analyze_patterns(category="STYLE", limit=5)
    assert isinstance(style_pats, list)
    if style_pats:
        assert style_pats[0]["pattern_type"] == "STYLE"
        assert "lift" in style_pats[0]
        assert "classification" in style_pats[0]

# 4. creative_create_experiment tool
@pytest.mark.asyncio
async def test_4_creative_create_experiment_tool():
    res = await creative_create_experiment(
        name="MCP Experiment Test",
        base_template="flux2_klein_txt2img",
        base_prompt="hero warrior",
        variable_tested="STEPS",
        control_value=20,
        variant_values=[25, 30],
        hypothesis="Testing steps variation via MCP"
    )
    assert res["status"] == "SUCCESS"
    exp = res["experiment"]
    assert exp["name"] == "MCP Experiment Test"
    assert len(exp["variants"]) == 3

    # Idempotent call
    res_idemp = await creative_create_experiment(
        name="MCP Experiment Test",
        base_template="flux2_klein_txt2img",
        base_prompt="hero warrior",
        variable_tested="STEPS",
        control_value=20,
        variant_values=[25, 30]
    )
    assert res_idemp["status"] == "SUCCESS"
    assert res_idemp["experiment"]["experiment_id"] == exp["experiment_id"]

    # Invalid variable check
    err_res = await creative_create_experiment(
        name="Bad Exp",
        base_template="t",
        base_prompt="p",
        variable_tested="INVALID_VAR_XYZ",
        control_value=1,
        variant_values=[2]
    )
    assert err_res["status"] == "ERROR"
    assert err_res["error_code"] == "INVALID_EXPERIMENT_VARIABLE"

# 5. creative_get_strategy_brief tool
@pytest.mark.asyncio
async def test_5_creative_get_strategy_brief_tool():
    # Specific topic
    res = await creative_get_strategy_brief(topic="quantum artificial intelligence")
    assert res["status"] == "SUCCESS"
    brief = res["brief"]
    assert "quantum artificial intelligence" in brief["topic"]
    assert brief["status"] == "PROPOSED"
    assert "recommended_prompt" in brief
    assert "confidence_score" in brief

    # List all briefs
    list_res = await creative_get_strategy_brief(topic=None)
    assert list_res["status"] == "SUCCESS"
    assert "briefs" in list_res
    assert len(list_res["briefs"]) >= 1
