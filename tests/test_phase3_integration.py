"""
Phase 3 — End-to-End Integration Test Suite.
Tests the FULL pipeline: Director → ContextManager → CapabilitySelector → DAG Engine →
WorkflowEngine → Scheduler → PluginManager → Agents → EventBus → StorageLayer → CacheLayer.

Run: python tests/test_phase3_integration.py
"""

import sys
import os
import asyncio
import time
import json
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# Ensure src is importable as package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.event_bus import bus, Event
from src.core.dag_engine import TaskDAG
from src.core.workflow_engine import Workflow, workflow_engine
from src.core.scheduler import Scheduler
from src.core.plugin_manager import plugin_manager
from src.core.context_manager import context_mgr
from src.storage.storage_layer import storage
from src.agents.computer_agent import ComputerAgent
from src.agents.media_agent import MediaAgent
from src.agents.research_agent import ResearchAgent
from src.agents.facebook_agent import FacebookAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def reset_singletons():
    """Reset shared singletons before each test."""
    bus.clear_history()
    bus._subscribers.clear()


# ── 1. DIRECTOR → RESEARCH PIPELINE (Full vertical slice) ───────────────────

@pytest.mark.asyncio
async def test_director_research_pipeline():
    reset_singletons()
    # Invalidate existing cache for this topic to ensure clean first run
    storage.set_cache("research", "research_integration test topic", None, ttl_sec=0)

    # Mock both BrowserAgent.search_web and capability_selector.generate
    mock_report = "Mocked research report on quantum computing milestones."
    mock_search_result = {
        "status": "success",
        "query": "Integration Test Topic",
        "results": ["Quantum computing milestone A.", "Quantum computing milestone B."],
        "sources": ["Mock Source 1"],
        "source": "duckduckgo_web",
    }
    with patch("src.providers.capability_selector.capability_selector.generate", return_value=mock_report), \
         patch("src.agents.browser_agent.browser_agent_instance.search_web",
               new_callable=AsyncMock, return_value=mock_search_result):
        # First call: should hit web search then LLM summarization
        res1 = await plugin_manager.invoke("research", "research", {"topic": "Integration Test Topic"})
        assert res1["status"] == "success"
        # Source is now "duckduckgo_web" (real search flow) instead of "llm"
        assert res1["source"] in ["duckduckgo_web", "cache"]
        assert res1["report"] is not None

        # Second call: same topic → should hit cache
        res2 = await plugin_manager.invoke("research", "research", {"topic": "Integration Test Topic"})
        assert res2["status"] == "success"
        assert res2["source"] == "cache"
        assert res2["report"] is not None



# ── 2. DAG PARALLEL EXECUTION (4-node concurrent graph) ─────────────────────

@pytest.mark.asyncio
async def test_dag_parallel_execution():
    reset_singletons()
    execution_order = []

    def node_a():
        execution_order.append("A")
        return "result_a"

    def node_b():
        execution_order.append("B")
        return "result_b"

    def node_c():
        execution_order.append("C")
        return "result_c"

    def node_d():
        execution_order.append("D")
        return "result_d"

    dag = TaskDAG(dag_id="integration_test_dag")
    dag.add_node("A", node_a)
    dag.add_node("B", node_b)
    dag.add_node("C", node_c)
    dag.add_node("D", node_d, dependencies=["A", "B"])

    results = await dag.execute_parallel()

    assert results["completed"] == 4
    assert results["failed"] == 0
    # D must execute after A and B
    assert execution_order.index("D") > execution_order.index("A")
    assert execution_order.index("D") > execution_order.index("B")

    # Verify reset and re-execution
    dag.reset()
    execution_order.clear()
    results2 = await dag.execute_parallel()
    assert results2["completed"] == 4


# ── 3. DAG NODE TIMEOUT ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dag_node_timeout():
    reset_singletons()
    async def slow_node():
        await asyncio.sleep(10)
        return "should_not_reach"

    def fast_node():
        return "fast_ok"

    dag = TaskDAG(dag_id="timeout_test_dag")
    dag.add_node("slow", slow_node, timeout_sec=0.2)
    dag.add_node("fast", fast_node)

    results = await dag.execute_parallel()

    assert results["node_results"]["slow"]["status"] == "failed"
    assert "Timeout" in results["node_results"]["slow"]["error"]
    assert results["node_results"]["fast"]["status"] == "success"
    assert results["completed"] == 1
    assert results["failed"] == 1


# ── 4. WORKFLOW ENGINE → MULTI-AGENT PIPELINE ───────────────────────────────

@pytest.mark.asyncio
async def test_workflow_engine_multi_step():
    reset_singletons()
    mock_report = "AI is transforming business operations in 2026."
    mock_copy = "Unlock the power of AI for your business! #AI #Growth"

    def step_research(ctx):
        ctx["research_done"] = True
        return mock_report

    def step_facebook(ctx):
        assert ctx.get("research_done") is True
        ctx["copy_done"] = True
        return mock_copy

    def step_media(ctx):
        assert ctx.get("copy_done") is True
        return {"gpu_target": "RUNPOD", "payload": "video_workflow"}

    wf = Workflow(workflow_id="integration_pipeline", name="Research-Facebook-Media Pipeline")
    wf.add_step("research", step_research, description="Gather research")
    wf.add_step("facebook", step_facebook, description="Generate copy")
    wf.add_step("media", step_media, description="Build media payload")

    workflow_engine.register_workflow(wf)
    result = await workflow_engine.execute_workflow("integration_pipeline", {})

    assert result["status"] == "success"
    assert len(result["results"]) == 3
    assert result["final_context"]["research_done"] is True
    assert result["final_context"]["copy_done"] is True


# ── 5. SCHEDULER RETRY RESILIENCE ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_scheduler_retry_resilience():
    reset_singletons()
    sched = Scheduler()
    await sched.start()

    call_count = {"n": 0}

    def flaky_task():
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise RuntimeError(f"Simulated failure #{call_count['n']}")
        return "finally_succeeded"

    await sched.submit("flaky_task", flaky_task, max_retries=3)

    # Wait for scheduler to process retries
    for _ in range(30):
        await asyncio.sleep(0.3)
        status = sched.get_task_status("flaky_task")
        if status and status["status"] in ("SUCCESS", "FAILED"):
            break

    await sched.stop()

    status = sched.get_task_status("flaky_task")
    assert status is not None
    assert status["status"] == "SUCCESS"
    assert status["result"] == "finally_succeeded"
    assert call_count["n"] == 3


# ── 6. EVENTBUS CROSS-MODULE COMMUNICATION ──────────────────────────────────

@pytest.mark.asyncio
async def test_eventbus_cross_module():
    reset_singletons()
    received = {"listener_a": [], "listener_b": [], "wildcard": []}

    def listener_a(event: Event):
        received["listener_a"].append(event.data)

    async def listener_b(event: Event):
        received["listener_b"].append(event.data)

    def wildcard_listener(event: Event):
        received["wildcard"].append(event.topic)

    bus.subscribe("agent.completed", listener_a)
    bus.subscribe("agent.completed", listener_b)
    bus.subscribe("*", wildcard_listener)

    await bus.publish("agent.completed", {"agent": "research", "result": "ok"}, sender="Director")
    await bus.publish("agent.completed", {"agent": "browser", "result": "done"}, sender="Director")
    await bus.publish("system.shutdown", {"reason": "test"}, sender="System")

    assert len(received["listener_a"]) == 2
    assert len(received["listener_b"]) == 2
    assert len(received["wildcard"]) == 3  # all 3 events via wildcard

    history = bus.get_history("agent.completed")
    assert len(history) == 2


# ── 7. EVENTBUS DEAD-LETTER QUEUE ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_eventbus_dead_letter_queue():
    reset_singletons()

    def failing_subscriber(event: Event):
        raise ValueError("Intentional test failure")

    bus.subscribe("test.fail", failing_subscriber)
    await bus.publish("test.fail", {"data": "should_fail"}, sender="test")

    dead = bus.get_dead_letters()
    assert len(dead) >= 1
    assert dead[-1]["topic"] == "test.fail"
    assert "Intentional test failure" in dead[-1]["error"]


# ── 8. SAFETY GATES INTEGRATION ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_safety_gates_integration():
    reset_singletons()
    # ComputerAgent: rmdir
    res_rm = await plugin_manager.invoke("computer", "run_command", {"command": "rmdir /s /q C:\\important"})
    assert res_rm["status"] == "approval_required"

    # ComputerAgent: del
    res_del = await plugin_manager.invoke("computer", "run_command", {"command": "del C:\\file.txt"})
    assert res_del["status"] == "approval_required"

    # FacebookAgent: publish
    res_pub = await plugin_manager.invoke("facebook", "publish_post", {"post_id": "123", "copy": "Test"})
    assert res_pub["status"] == "approval_required"


# ── 9. CACHE TOKEN SAVINGS ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cache_token_savings():
    reset_singletons()
    call_counter = {"n": 0}

    def counting_generate(prompt, capability="general", system_prompt=None):
        call_counter["n"] += 1
        return f"Mocked response #{call_counter['n']}"

    with patch("src.providers.capability_selector.capability_selector.generate", side_effect=counting_generate):
        # Clear any prior cache for this key
        topic = "Unique Cache Savings Test Topic"
        storage.cache.set("research", f"research_{topic.lower()}", None, ttl_sec=0)

        res1 = await plugin_manager.invoke("research", "research", {"topic": topic})
        assert call_counter["n"] == 1  # LLM called once

        res2 = await plugin_manager.invoke("research", "research", {"topic": topic})
        assert call_counter["n"] == 1  # LLM NOT called again — cache hit
        assert res2["source"] == "cache"


# ── 10. CONTEXT MANAGER STATE PERSISTENCE ────────────────────────────────────

def test_context_manager_state_roundtrip():
    reset_singletons()
    test_content = json.dumps({"phase": 3, "status": "integration_test"})
    context_mgr.write_state_file("_integration_test.json", test_content)
    
    read_back = context_mgr.read_state_file("_integration_test.json")
    parsed = json.loads(read_back)
    assert parsed["phase"] == 3
    assert parsed["status"] == "integration_test"

    # Cleanup
    test_file = context_mgr.state_dir / "_integration_test.json"
    if test_file.exists():
        test_file.unlink()


# ── 11. STORAGE LAYER ROUNDTRIP ──────────────────────────────────────────────

def test_storage_layer_full_roundtrip():
    reset_singletons()
    # SQLite roundtrip
    record_id = storage.save_record("integration_test", "Test Record", "Integration test content", ["phase3", "test"])
    assert record_id > 0

    results = storage.search_records("Integration test", category="integration_test")
    assert len(results) >= 1
    assert any(r["title"] == "Test Record" for r in results)

    # Artifact roundtrip
    storage.save_artifact("_integration_test.txt", "Phase 3 integration artifact")
    content = storage.read_artifact("_integration_test.txt")
    assert content == "Phase 3 integration artifact"

    # Cleanup
    artifact_path = storage.artifacts_dir / "_integration_test.txt"
    if artifact_path.exists():
        artifact_path.unlink()


# ── RUNNER ───────────────────────────────────────────────────────────────────

async def run_all_tests():
    tests = [
        ("Director -> Research Pipeline", test_director_research_pipeline),
        ("DAG Parallel Execution", test_dag_parallel_execution),
        ("DAG Node Timeout", test_dag_node_timeout),
        ("Workflow Engine Multi-Step", test_workflow_engine_multi_step),
        ("Scheduler Retry Resilience", test_scheduler_retry_resilience),
        ("EventBus Cross-Module", test_eventbus_cross_module),
        ("EventBus Dead-Letter Queue", test_eventbus_dead_letter_queue),
        ("Safety Gates Integration", test_safety_gates_integration),
        ("Cache Token Savings", test_cache_token_savings),
        ("ContextManager State Roundtrip", lambda: asyncio.sleep(0) or test_context_manager_state_roundtrip()),
        ("StorageLayer Full Roundtrip", lambda: asyncio.sleep(0) or test_storage_layer_full_roundtrip()),
    ]

    passed = 0
    failed = 0
    print("\n================ RUNNING PHASE 3 INTEGRATION TESTS ================\n")
    for name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                await test_func()
            else:
                res = test_func()
                if asyncio.iscoroutine(res):
                    await res
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name} - {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\nSummary: {passed} PASSED, {failed} FAILED out of {len(tests)} tests.")
    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_all_tests())
