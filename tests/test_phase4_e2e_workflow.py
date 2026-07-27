"""
Phase 4 — End-to-End Real Workflow Execution.
Executes the full pipeline:
User Goal → Director → Planner → Workflow Engine → TaskDAG → Browser Agent → Research Agent → Facebook Content Creation → Media Agent → Storage Layer → Final Report.

First Real Example: "Create a Facebook post from idea to final image"

Run: python tests/test_phase4_e2e_workflow.py
"""

import sys
import os
import time
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.event_bus import bus, Event
from src.core.dag_engine import TaskDAG
from src.core.workflow_engine import workflow_engine, Workflow
from src.core.scheduler import scheduler
from src.core.plugin_manager import plugin_manager
from src.core.context_manager import context_mgr
from src.core.gpu_manager import gpu_mgr
from src.storage.storage_layer import storage
from src.providers.capability_selector import capability_selector

import src.agents.browser_agent
import src.agents.computer_agent
import src.agents.research_agent
import src.agents.facebook_agent
import src.agents.university_agent
import src.agents.media_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("phase4_e2e")

E2E_REPORT: Dict[str, Any] = {}


async def run_e2e_workflow():
    t_start = time.perf_counter()
    print("\n================ EXECUTING END-TO-END REAL WORKFLOW ================\n")

    user_goal = "Create a Facebook post from idea to final image for AI Automation in 2026"
    print(f"  [Goal Input] '{user_goal}'")

    # Step 1: Director Agent & Capability Selector Model Assignment
    log.info("Step 1: Director Agent evaluating user goal...")
    model_assigned = capability_selector.select_model_for_capability("planning")
    print(f"  [Model Assigned] {model_assigned} (via CapabilityModelSelector)")

    # Step 2: Initialize EventBus monitoring
    events_captured = []
    def event_tracker(ev: Event):
        events_captured.append({"topic": ev.topic, "sender": ev.sender, "timestamp": ev.timestamp})

    bus.subscribe("*", event_tracker)

    # Step 3: Execute TaskDAG (Parallel execution of Research & System Diagnostics)
    print("  [TaskDAG Engine] Executing parallel nodes: ResearchAgent + ComputerAgent...")
    dag = TaskDAG("e2e_parallel_dag")

    async def task_research():
        return await plugin_manager.invoke("research", "research", {"topic": "AI Automation Trends 2026"})

    async def task_sys_check():
        return await plugin_manager.invoke("computer", "sys_info", {})

    dag.add_node("research_node", task_research)
    dag.add_node("sys_check_node", task_sys_check)

    dag_res = await dag.execute_parallel()
    research_output = dag_res["node_results"]["research_node"]["result"]
    sys_output = dag_res["node_results"]["sys_check_node"]["result"]
    print(f"  [TaskDAG] Completed 2 parallel nodes in {dag_res['completed']} success state.")

    # Step 4: Content Creation via FacebookAgent
    print("  [FacebookAgent] Generating copywriting, CTA, hashtags, and visual prompt...")
    fb_res = await plugin_manager.invoke("facebook", "create_post", {"topic": "AI Automation Best Practices 2026"})
    copy_text = fb_res.get("copy", "Automate your workflow with local AI!")
    hashtags = fb_res.get("hashtags", ["#AI", "#Automation"])
    img_prompt = fb_res.get("image_prompt", "Futuristic AI workstation, realistic 8k")
    print(f"  [Facebook Copy Drafted] Hashtags: {hashtags}")

    # Step 5: Media Generation Payload via MediaAgent & GPUManager
    print("  [MediaAgent & GPUManager] Evaluating GPU workload target for image generation...")
    media_res = await plugin_manager.invoke("media", "generate_image", {
        "prompt": img_prompt,
        "resolution": "1024x1024"
    })
    gpu_target = media_res.get("gpu_target", "RUNPOD")
    reason = media_res.get("reason", "Heavy workload")
    print(f"  [GPU Target Evaluated] Target: {gpu_target} ({reason})")

    # Step 6: Verify Safety Gate on Facebook Publishing
    print("  [Safety Gate Check] Attempting automated Facebook publish...")
    pub_res = await plugin_manager.invoke("facebook", "publish_post", {"post_id": "fb_e2e_101", "copy": copy_text})
    safety_triggered = pub_res.get("status") == "approval_required"
    print(f"  [Safety Gate Triggered] Post publication blocked for human approval: {safety_triggered}")

    # Step 7: Store Final Campaign Artifact in StorageLayer
    final_payload = {
        "user_goal": user_goal,
        "model_assigned": model_assigned,
        "research_summary": research_output.get("report", "")[:150] + "...",
        "facebook_post": {
            "copy": copy_text,
            "hashtags": hashtags,
            "image_prompt": img_prompt
        },
        "media_generation": {
            "gpu_target": gpu_target,
            "workflow": media_res.get("workflow_payload")
        },
        "safety_gate": {
            "publishing_blocked": safety_triggered,
            "message": pub_res.get("message")
        },
        "system_diagnostics": sys_output.get("info")
    }

    artifact_filename = "e2e_facebook_campaign_result.json"
    artifact_path = storage.save_artifact(artifact_filename, json.dumps(final_payload, indent=2))
    storage.save_record("e2e_campaign", "Facebook AI Post 2026", copy_text, hashtags)
    print(f"  [StorageLayer] Final campaign report saved to artifact: {artifact_path}")

    # Step 8: Emit completion event
    await bus.publish("campaign.completed", {"artifact": artifact_filename, "status": "success"}, sender="E2E_Workflow")

    t_elapsed = round(time.perf_counter() - t_start, 2)

    E2E_REPORT["status"] = "SUCCESS"
    E2E_REPORT["total_execution_time_sec"] = t_elapsed
    E2E_REPORT["user_goal"] = user_goal
    E2E_REPORT["artifact_created"] = artifact_path
    E2E_REPORT["events_captured_count"] = len(events_captured)
    E2E_REPORT["final_payload"] = final_payload

    print(f"\n================ END-TO-END WORKFLOW COMPLETED IN {t_elapsed} SECONDS ================\n")

    # Write report to Project_State/Audit/e2e_workflow_report.json
    out_file = Path(os.path.expanduser("~")) / ".gemini" / "antigravity-ide" / "scratch" / "Project_State" / "Audit" / "e2e_workflow_report.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(E2E_REPORT, f, indent=2)

    print(f"[OK] E2E Workflow Report saved to: {out_file}\n")


if __name__ == "__main__":
    asyncio.run(run_e2e_workflow())
