"""
Lightweight Director Agent.
Receives user goals, delegates context to Planner/DAG Engine, and triggers Workflows.
Strict Rule: No business logic inside Director Agent.
"""

import asyncio
import logging
from typing import Dict, Any, List

from ..core.event_bus import bus, Event
from ..core.context_manager import context_mgr
from ..core.workflow_engine import workflow_engine
from ..core.dag_engine import TaskDAG
from ..core.gpu_manager import gpu_mgr
from ..storage.storage_layer import storage
from ..providers.capability_selector import capability_selector

log = logging.getLogger("director_lightweight")

class DirectorAgent:
    def __init__(self, name: str = "Director"):
        self.name = name
        self.active = True

    async def handle_goal(self, goal: str, workflow_id: str = None) -> Dict[str, Any]:
        """
        Lightweight Goal Delegation:
        1. Query cache via Storage Layer
        2. Select model via Capability Selector
        3. If workflow requested -> Trigger Workflow Engine directly
        4. Otherwise -> Delegate to Planner DAG Engine
        """
        if not self.active:
            return {"status": "error", "message": "Director Agent is stopped."}

        log.info(f"[Lightweight Director] Received goal: '{goal}'")

        # 1. Storage Layer Cache Check
        cached = storage.get_cache("goal", goal)
        if cached:
            log.info("[Lightweight Director] Cache HIT.")
            return {"status": "success", "source": "cache", "result": cached}

        # 2. Trigger Workflow directly if requested
        if workflow_id and workflow_id in workflow_engine.registered_workflows:
            log.info(f"[Lightweight Director] Delegating to WorkflowEngine: '{workflow_id}'")
            wf_res = await workflow_engine.execute_workflow(workflow_id, {"goal": goal})
            storage.set_cache("goal", goal, wf_res)
            return {"status": "success", "source": "workflow_engine", "result": wf_res}

        # 3. Otherwise delegate goal to Planner DAG
        log.info("[Lightweight Director] Delegating goal to Capability Selector & DAG Engine...")
        model = capability_selector.select_model_for_capability("planning")
        
        reasoning = capability_selector.generate(
            prompt=f"Goal: {goal}. Provide a high-level 3-step breakdown.",
            capability="planning"
        )

        response = {
            "model_assigned": model,
            "orchestration": reasoning
        }

        # Save to Storage Layer & Cache
        storage.set_cache("goal", goal, response)
        storage.save_record("director_goal", goal[:40], reasoning)
        await bus.publish("director.goal_processed", {"goal": goal, "result": response}, sender=self.name)

        return {"status": "success", "source": "planner_dag", "result": response}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    director = DirectorAgent()
    res = asyncio.run(director.handle_goal("Publish daily marketing video batch"))
    print("\n--- LIGHTWEIGHT DIRECTOR RESULT ---")
    import json
    print(json.dumps(res, indent=2))
