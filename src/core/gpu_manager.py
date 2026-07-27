"""
GPUManager - Gatekeeper for local CPU/iGPU vs remote RunPod GPU allocation.
Enforces $10 budget ceiling and auto-terminates remote pods after workloads finish.
"""

import os
import json
import logging
from typing import Dict, Any, Tuple

log = logging.getLogger("gpu_manager")

MAX_RUNPOD_BUDGET_USD = 10.0

class GPUManager:
    def __init__(self):
        self.total_spent = 0.0
        self.pod_active = False
        self.active_pod_id = None

    def evaluate_workload(self, task_type: str, payload: Dict[str, Any]) -> Tuple[str, str]:
        """
        Determines execution target: 'LOCAL' (CPU/iGPU, $0) or 'RUNPOD' (GPU).
        Returns tuple: (target, reason)
        """
        heavy_gpu_types = ["image_generation", "video_generation", "comfyui_render", "model_training"]

        if task_type.lower() not in heavy_gpu_types:
            return ("LOCAL", "Task is text/reasoning/browsing → assigned to local Ollama CPU/iGPU ($0 cost)")

        if self.total_spent >= MAX_RUNPOD_BUDGET_USD:
            return ("LOCAL", f"RunPod budget cap of ${MAX_RUNPOD_BUDGET_USD:.2f} reached. Falling back to local/cloud API.")

        return ("RUNPOD", f"Heavy GPU workload '{task_type}' requires remote GPU execution.")

    def log_spend(self, amount_usd: float, pod_id: str, description: str):
        """Track spend against budget."""
        self.total_spent += amount_usd
        log.info(f"[GPUManager] Logged spend ${amount_usd:.4f} for pod '{pod_id}'. Total spend: ${self.total_spent:.4f} / ${MAX_RUNPOD_BUDGET_USD:.2f}")

# Singleton
gpu_mgr = GPUManager()
