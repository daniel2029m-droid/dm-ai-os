"""
PocketFlowAdapter — P4 Open Source Integration (Fase C)
========================================================
Wraps PocketFlow (https://github.com/The-Pocket/PocketFlow) as an optional
workflow engine backend.

PocketFlow es un framework minimalista de grafos de flujo para LLMs (<100 lineas core)
que ofrece:
- Nodos async y flujos en paralelo (BatchFlow / AsyncFlow)
- Ejecucion deterministica de grafos DAG sin opinion de arquitectura
- Visualizacion nativa de flujos y estado
- Opt-in puro: 100% aislado sin modificar WorkflowEngine ni DAGEngine

Patron DM AI OS:
- _is_available() verifica instalacion antes de invocar.
- Si no disponible: retorna None y WorkflowEngine usa su ejecucion nativa.
- POCKETFLOW_ENABLED=true en .env para activar (opt-in).

NO modifica DAGEngine ni ninguna capa congelada.
"""

import os
import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable

log = logging.getLogger("pocketflow_adapter")


class PocketFlowAdapter:
    """Thin adapter wrapping PocketFlow for parallel/graph flow execution."""

    _ENABLED_ENV = "POCKETFLOW_ENABLED"

    @staticmethod
    def _is_available() -> bool:
        """Check if pocketflow library is installed."""
        try:
            import pocketflow  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _is_enabled() -> bool:
        """Check POCKETFLOW_ENABLED env var (defaults to False — opt-in)."""
        return os.getenv("POCKETFLOW_ENABLED", "false").lower() in ("true", "1", "yes")

    def run_flow(
        self,
        nodes_def: List[Dict[str, Any]],
        initial_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Run a workflow using PocketFlow engine.

        Args:
            nodes_def: List of dicts describing nodes:
                [{"name": str, "action": callable, "params": dict}, ...]
            initial_params: Initial context dict.

        Returns:
            Dict with execution results:
                {"status": "success", "results": dict, "source": "pocketflow"}
            or None if disabled/unavailable/failed.
        """
        if not self._is_enabled():
            log.debug("[PocketFlowAdapter] Disabled (POCKETFLOW_ENABLED != true).")
            return None

        if not self._is_available():
            log.warning(
                "[PocketFlowAdapter] pocketflow not installed. "
                "Install: pip install pocketflow. Falling back to native WorkflowEngine."
            )
            return None

        try:
            return self._do_run_flow(nodes_def, initial_params or {})
        except Exception as e:
            log.warning(f"[PocketFlowAdapter] Flow execution failed: {e}")
            return None

    def _do_run_flow(
        self,
        nodes_def: List[Dict[str, Any]],
        initial_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        from pocketflow import Node, Flow

        context = dict(initial_params)
        results = {}

        # Create PocketFlow Node for each definition
        flow_nodes = []
        for n_def in nodes_def:
            name = n_def.get("name", "step")
            action = n_def.get("action")

            class CustomNode(Node):
                def __init__(self, node_name: str, fn: Callable):
                    super().__init__()
                    self.node_name = node_name
                    self.fn = fn

                def prep(self, shared):
                    return shared

                def exec(self, prep_res):
                    if asyncio.iscoroutinefunction(self.fn):
                        return asyncio.run(self.fn(prep_res))
                    return self.fn(prep_res)

                def post(self, shared, prep_res, exec_res):
                    shared[self.node_name] = exec_res
                    results[self.node_name] = exec_res
                    return "default"

            flow_nodes.append(CustomNode(name, action))

        # Chain nodes sequentially in PocketFlow
        if flow_nodes:
            first_node = flow_nodes[0]
            curr = first_node
            for next_n in flow_nodes[1:]:
                curr >> next_n
                curr = next_n

            flow = Flow(start=first_node)
            flow.run(shared=context)

        log.info(f"[PocketFlowAdapter] Executed {len(nodes_def)} steps via PocketFlow")
        return {
            "status": "success",
            "results": results,
            "final_context": context,
            "source": "pocketflow",
        }


# Module-level singleton
pocketflow_adapter = PocketFlowAdapter()
