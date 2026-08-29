"""
DM AI OS — Compute Plane Orchestrator
=====================================
Central orchestrator for the remote GPU Compute Plane (Google Colab Tesla T4 / ComfyUI).

Manages complete lifecycle:
  - READY: Active worker, verified GPU (Tesla T4), ComfyUI responsive, queue ready.
  - STARTING / BOOTSTRAPPING: Handshake received, waiting for ComfyUI /system_stats probe.
  - RECONNECTING: Worker lost heartbeat recently (< 90s), awaiting tunnel renewal.
  - REQUIRES_ACTIVATION: No active worker. Provides legitimate 1-click Colab activation URL.
  - OFFLINE: Compute plane unavailable.

Enforces strict routing:
  - EXPLICIT ComfyUI requests: Never silent-fallback to NVIDIA NIM if Colab is offline. Returns REQUIRES_ACTIVATION.
  - AUTO mode: Prioritizes ComfyUI when READY; falls back gracefully to cloud providers when offline with truthful telemetry.
"""

import os
import time
import logging
from enum import Enum
from typing import Dict, Any, Optional, Tuple, List

from ..providers.worker_registry import worker_registry, WorkerStatus
from ..core.comfy_health_probe import comfy_health_probe

log = logging.getLogger("compute_plane_orchestrator")

COLAB_NOTEBOOK_GITHUB_URL = "https://colab.research.google.com/github/daniel2029m-droid/dm-ai-os/blob/main/deployment/colab_comfyui_t4.ipynb"


class ComputeState(str, Enum):
    READY = "ready"
    STARTING = "starting"
    BOOTSTRAPPING = "bootstrapping"
    CONNECTING = "connecting"
    DEGRADED = "degraded"
    REQUIRES_ACTIVATION = "requires_activation"
    OFFLINE = "offline"
    FAILED = "failed"


class ComputePlaneOrchestrator:
    """
    Orchestrates and verifies the compute plane state and provides legitimate activation workflows.
    """

    def __init__(self):
        self.notebook_url = os.getenv("DM_COLAB_NOTEBOOK_URL", COLAB_NOTEBOOK_GITHUB_URL)

    def get_compute_status(self) -> Dict[str, Any]:
        """
        Evaluates the physical and logical state of the Compute Plane.
        Returns state, worker metadata, and 1-click activation link if offline.
        """
        active_worker = worker_registry.get_active_worker()
        all_workers = worker_registry.list_workers()

        if active_worker and active_worker.get("status") == WorkerStatus.READY.value:
            return {
                "state": ComputeState.READY.value,
                "status": "ready",
                "backend": "google-colab",
                "provider": "comfyui",
                "worker_id": active_worker.get("worker_id"),
                "session_id": active_worker.get("session_id"),
                "gpu_name": active_worker.get("gpu_name", "NVIDIA Tesla T4"),
                "vram_gb": active_worker.get("vram_gb", 16.0),
                "endpoint": active_worker.get("endpoint"),
                "models": active_worker.get("models", []),
                "requires_activation": False,
                "activation_url": None,
                "message": "Compute Plane READY (Tesla T4 16GB)"
            }

        # Check if any worker is reconnecting or registering
        if any(w.get("status") == WorkerStatus.RECONNECTING.value for w in all_workers):
            return {
                "state": ComputeState.CONNECTING.value,
                "status": "reconnecting",
                "backend": "google-colab",
                "provider": "comfyui",
                "requires_activation": False,
                "activation_url": None,
                "message": "Worker reconectando / renovando túnel..."
            }

        # Worker is offline -> Requires legitimate Colab activation
        return {
            "state": ComputeState.REQUIRES_ACTIVATION.value,
            "status": "requires_activation",
            "backend": "google-colab",
            "provider": "comfyui",
            "requires_activation": True,
            "activation_url": self.notebook_url,
            "message": "Google Colab offline. Requiere activación en 1 clic."
        }

    async def ensure_compute_ready(
        self,
        timeout_sec: float = 10.0,
        allow_fallback: bool = True
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Validates that a healthy, probed ComfyUI worker is ready.
        If offline and allow_fallback is False, raises clean error requiring activation.
        """
        active_worker = worker_registry.get_active_worker()

        if not active_worker:
            if not allow_fallback:
                return False, None, "Google Colab está apagado. Pulsa 'Activar Compute Plane' para iniciar el runtime T4."
            return False, None, "No active worker"

        # Verify probe health
        probe_res = await comfy_health_probe.verify_and_update_worker(active_worker["worker_id"])
        if probe_res.get("status") == "ready":
            return True, active_worker, None

        err = probe_res.get("error", "ComfyUI probe failed")
        if not allow_fallback:
            return False, None, f"ComfyUI en Colab no responde ({err}). Requiere reactivación."

        return False, None, err

    def get_activation_url(self) -> str:
        """Returns the legitimate 1-click Colab notebook activation link."""
        return self.notebook_url


compute_plane_orchestrator = ComputePlaneOrchestrator()
