"""
DAG Engine - Directed Acyclic Graph Task Execution Model.
Executes independent task nodes concurrently in parallel while respecting dependency graphs.
"""

import asyncio
import logging
from typing import Dict, Any, List, Set, Callable, Optional
from dataclasses import dataclass, field

log = logging.getLogger("dag_engine")

DEFAULT_NODE_TIMEOUT_SEC = 60

@dataclass
class DAGNode:
    node_id: str
    action: Callable[[], Any]
    dependencies: Set[str] = field(default_factory=set)
    timeout_sec: float = DEFAULT_NODE_TIMEOUT_SEC
    result: Any = None
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED

class TaskDAG:
    def __init__(self, dag_id: str):
        self.dag_id = dag_id
        self.nodes: Dict[str, DAGNode] = {}

    def add_node(self, node_id: str, action: Callable[[], Any], dependencies: List[str] = None, timeout_sec: float = DEFAULT_NODE_TIMEOUT_SEC):
        deps = set(dependencies) if dependencies else set()
        self.nodes[node_id] = DAGNode(node_id=node_id, action=action, dependencies=deps, timeout_sec=timeout_sec)

    def reset(self):
        """Reset all node states to PENDING so the DAG can be re-executed."""
        for node in self.nodes.values():
            node.status = "PENDING"
            node.result = None

    async def execute_parallel(self) -> Dict[str, Any]:
        """Execute DAG nodes concurrently in parallel topological batches."""
        completed: Set[str] = set()
        failed: Set[str] = set()
        results: Dict[str, Any] = {}

        log.info(f"[DAGEngine] Executing DAG '{self.dag_id}' with {len(self.nodes)} nodes.")

        while len(completed) + len(failed) < len(self.nodes):
            # Find nodes ready to run (dependencies met, not yet running/done)
            ready_nodes = [
                node for node in self.nodes.values()
                if node.status == "PENDING" and node.dependencies.issubset(completed)
            ]

            if not ready_nodes:
                if len(completed) + len(failed) < len(self.nodes):
                    log.error(f"[DAGEngine] Deadlock or unresolvable dependency in DAG '{self.dag_id}'")
                    break

            log.info(f"[DAGEngine] Batch executing {len(ready_nodes)} parallel nodes: {[n.node_id for n in ready_nodes]}")

            # Run batch concurrently
            async def _run_node(node: DAGNode):
                node.status = "RUNNING"
                try:
                    if asyncio.iscoroutinefunction(node.action):
                        res = await asyncio.wait_for(node.action(), timeout=node.timeout_sec)
                    else:
                        res = node.action()
                    node.result = res
                    node.status = "COMPLETED"
                    completed.add(node.node_id)
                    results[node.node_id] = {"status": "success", "result": res}
                except asyncio.TimeoutError:
                    node.status = "FAILED"
                    failed.add(node.node_id)
                    results[node.node_id] = {"status": "failed", "error": f"Timeout after {node.timeout_sec}s"}
                    log.error(f"[DAGEngine] Node '{node.node_id}' timed out after {node.timeout_sec}s.")
                except Exception as e:
                    node.status = "FAILED"
                    failed.add(node.node_id)
                    results[node.node_id] = {"status": "failed", "error": str(e)}

            await asyncio.gather(*[_run_node(n) for n in ready_nodes])

        return {
            "dag_id": self.dag_id,
            "total_nodes": len(self.nodes),
            "completed": len(completed),
            "failed": len(failed),
            "node_results": results
        }

