"""
DM AI OS — ModelRouter & Dispatch Authority
===========================================
Primary authority deciding execution target:
  - LOCAL: Allowed only for text reasoning, memory, or ultra-lightweight CPU tasks.
  - REMOTE_GPU: Dispatched to active Google Colab Tesla T4 (or other GPU worker) via ComfyUI.
  - CLOUD_API: Fallback to commercial APIs (NVIDIA NIM / Higgsfield) when configured.
  - REQUIRES_ACTIVATION: GPU worker offline; prompts 1-click Colab activation.
  - QUEUED: Job persisted awaiting compute resources.

HARD GUARDRAIL:
  Pachu (AMD Ryzen 5 4600G iGPU) NEVER runs heavy visual generation (Z-Image, FLUX, LTX, H3, SeedVR2, FLOAT).
"""

import os
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple

from .model_registry import model_registry, ModelValidationError
from ..providers.worker_registry import worker_registry, WorkerStatus
from .compute_plane_orchestrator import COLAB_NOTEBOOK_GITHUB_URL

log = logging.getLogger("model_router")


class ExecutionTarget(str, Enum):
    LOCAL = "LOCAL"
    REMOTE_GPU = "REMOTE_GPU"
    CLOUD_API = "CLOUD_API"
    QUEUED = "QUEUED"
    REQUIRES_ACTIVATION = "REQUIRES_ACTIVATION"


@dataclass
class RouteDecision:
    target: ExecutionTarget
    model_id: str
    model_info: Dict[str, Any]
    worker: Optional[Dict[str, Any]] = None
    reason: str = ""
    activation_url: Optional[str] = None
    estimated_vram_gb: float = 0.0
    fallback_available: bool = False


class ModelRouter:
    """
    Evaluates hardware constraints, worker readiness, and task profiles to route AI workloads safely.
    """

    def __init__(self):
        self.notebook_url = os.getenv("DM_COLAB_NOTEBOOK_URL", COLAB_NOTEBOOK_GITHUB_URL)

    def route_intent(
        self,
        task_type: str,
        prompt: str = "",
        model_name: Optional[str] = None,
        preferred_target: Optional[str] = None,
        allow_cloud_fallback: bool = False
    ) -> RouteDecision:
        task_clean = task_type.lower().strip()
        heavy_tasks = ["image_generation", "text_to_image", "video_generation", "text_to_video",
                       "image_to_video", "super_resolution", "upscale", "lipsync"]
        is_heavy_task = any(ht in task_clean for ht in heavy_tasks)


        # 1. Resolve target model
        if model_name:
            model_info = model_registry.get_model(model_name)
            if not model_info:
                model_info = model_registry.find_best_model_for_task(task_clean)
        else:
            model_info = model_registry.find_best_model_for_task(task_clean)

        if not model_info:
            if not is_heavy_task:
                model_info = {
                    "model_id": f"local_{task_clean}",
                    "display_name": f"Local {task_clean.title()}",
                    "local_allowed": True,
                    "min_vram_gb": 0.0
                }
            elif "image" in task_clean:
                model_info = model_registry.get_model("zimage_turbo") or model_registry.get_model("sd15_base") or {}
            else:
                model_info = model_registry.get_model("ltx_video") or {}

        model_id = model_info.get("model_id", "unknown_model")
        min_vram = model_info.get("min_vram_gb", 0.0)
        local_allowed = model_info.get("local_allowed", False)


        # 2. Check if task can run locally on Pachu
        heavy_tasks = ["image_generation", "text_to_image", "video_generation", "text_to_video",
                       "image_to_video", "super_resolution", "upscale", "lipsync"]
        is_heavy_task = any(ht in task_clean for ht in heavy_tasks)

        if not is_heavy_task and local_allowed:
            return RouteDecision(
                target=ExecutionTarget.LOCAL,
                model_id=model_id,
                model_info=model_info,
                reason="Task is lightweight and permitted on local CPU/iGPU ($0 compute cost)."
            )

        # 3. Task requires GPU — Check remote compute plane (Google Colab Tesla T4)
        active_worker = worker_registry.get_active_worker()

        if active_worker and active_worker.get("status") == WorkerStatus.READY.value:
            worker_vram = float(active_worker.get("vram_gb", 16.0))
            worker_gpu = active_worker.get("gpu_name", "NVIDIA GPU")

            # Check VRAM requirement
            if min_vram > worker_vram:
                log.warning(f"[ModelRouter] Model '{model_id}' requires {min_vram}GB VRAM > worker {worker_vram}GB.")
                return RouteDecision(
                    target=ExecutionTarget.QUEUED,
                    model_id=model_id,
                    model_info=model_info,
                    worker=active_worker,
                    reason=f"Model '{model_id}' requires {min_vram} GB VRAM, exceeding active worker capacity ({worker_vram} GB).",
                    estimated_vram_gb=min_vram
                )

            return RouteDecision(
                target=ExecutionTarget.REMOTE_GPU,
                model_id=model_id,
                model_info=model_info,
                worker=active_worker,
                reason=f"Routed to remote GPU worker '{active_worker.get('worker_id')}' ({worker_gpu}, {worker_vram}GB VRAM).",
                estimated_vram_gb=min_vram
            )

        # 4. GPU is offline -> Enforce Pachu Guardrail (NEVER run heavy models locally)
        log.info(f"[ModelRouter] Remote GPU worker offline for heavy task '{task_type}'. Yielding REQUIRES_ACTIVATION.")
        return RouteDecision(
            target=ExecutionTarget.REQUIRES_ACTIVATION,
            model_id=model_id,
            model_info=model_info,
            reason="GPU worker offline. Pachu local hardware cannot execute heavy visual generation. Activate Google Colab T4 worker.",
            activation_url=self.notebook_url,
            estimated_vram_gb=min_vram
        )

    def get_capability_matrix(self) -> Dict[str, Any]:
        """
        Returns dynamic capability matrix mapping registered models against hardware targets.
        """
        models = model_registry.list_models()
        active_worker = worker_registry.get_active_worker()
        worker_ready = bool(active_worker and active_worker.get("status") == WorkerStatus.READY.value)
        worker_vram = float(active_worker.get("vram_gb", 0.0)) if worker_ready else 0.0

        matrix = []
        for m in models:
            min_vram = m.get("min_vram_gb", 0.0)
            local_compat = m.get("local_allowed", False)
            t4_compat = (min_vram <= 16.0)

            # Real-time availability
            if worker_ready and min_vram <= worker_vram:
                availability = "ONLINE_READY"
            elif local_compat:
                availability = "LOCAL_AVAILABLE"
            else:
                availability = "REQUIRES_GPU_WORKER"

            matrix.append({
                "model_id": m.get("model_id"),
                "display_name": m.get("display_name"),
                "family": m.get("family"),
                "task_types": m.get("task_types", []),
                "min_vram_gb": min_vram,
                "pachu_compatible": local_compat,
                "t4_16gb_compatible": t4_compat,
                "availability": availability
            })

        return {
            "worker_status": active_worker.get("status") if active_worker else "offline",
            "active_gpu": active_worker.get("gpu_name") if active_worker else None,
            "active_vram_gb": worker_vram,
            "models": matrix
        }


# Global singleton
model_router = ModelRouter()
