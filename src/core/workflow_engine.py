"""
WorkflowEngine - Executes reusable, multi-step deterministic workflows
independent of the Director Agent.
"""

import asyncio
import logging
from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass, field

log = logging.getLogger("workflow_engine")

@dataclass
class WorkflowStep:
    name: str
    action: Callable[[Dict[str, Any]], Any]
    description: str = ""

class Workflow:
    def __init__(self, workflow_id: str, name: str):
        self.workflow_id = workflow_id
        self.name = name
        self.steps: List[WorkflowStep] = []

    def add_step(self, name: str, action: Callable[[Dict[str, Any]], Any], description: str = ""):
        self.steps.append(WorkflowStep(name=name, action=action, description=description))
        return self

class WorkflowEngine:
    def __init__(self):
        self.registered_workflows: Dict[str, Workflow] = {}

    def register_workflow(self, workflow: Workflow):
        self.registered_workflows[workflow.workflow_id] = workflow
        log.info(f"[WorkflowEngine] Registered workflow '{workflow.workflow_id}' ({workflow.name})")

    async def execute_workflow(self, workflow_id: str, initial_context: Dict[str, Any] = None) -> Dict[str, Any]:
        if workflow_id not in self.registered_workflows:
            log.error(f"[WorkflowEngine] Workflow '{workflow_id}' not found.")
            return {"status": "error", "message": f"Workflow '{workflow_id}' not registered."}

        wf = self.registered_workflows[workflow_id]
        context = initial_context or {}
        log.info(f"[WorkflowEngine] Executing workflow '{wf.name}' ({len(wf.steps)} steps)")

        results = []
        for step in wf.steps:
            log.info(f"[WorkflowEngine] Step: '{step.name}'...")
            try:
                if asyncio.iscoroutinefunction(step.action):
                    res = await step.action(context)
                else:
                    res = step.action(context)
                
                context[step.name] = res
                results.append({"step": step.name, "status": "success", "result": res})
            except Exception as e:
                log.error(f"[WorkflowEngine] Step '{step.name}' failed: {e}")
                results.append({"step": step.name, "status": "failed", "error": str(e)})
                return {"status": "failed", "failed_step": step.name, "results": results}

        return {"status": "success", "workflow": wf.name, "results": results, "final_context": context}

# Singleton
workflow_engine = WorkflowEngine()
