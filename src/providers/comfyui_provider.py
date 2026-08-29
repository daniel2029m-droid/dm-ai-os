"""
DM AI OS — ComfyUI Remote Provider Adapter
==========================================
Integrates ComfyUI running on Google Colab (Tesla T4 16GB) or remote GPU workers
directly into the ProviderManager router.

Delegates execution to CreativeEngine and Auto-Vaults outputs into Project_State/Artifacts/media/<job_id>/.
Generates HMAC-SHA256 presigned streaming URLs for zero-leak delivery to the iPhone PWA.
"""

import time
import logging
from typing import Dict, Any, List, Tuple, Optional

from .provider_manager import BaseProviderAdapter, ProviderStatus, ProviderCapability
from .provider_history import provider_history
from .worker_registry import worker_registry, WorkerStatus
from ..core.creative_engine import creative_engine
from ..core.comfy_health_probe import comfy_health_probe
from ..api.creative_assets_router import generate_signed_urls

log = logging.getLogger("comfyui_provider")


class ComfyUIProviderAdapter(BaseProviderAdapter):
    """
    ComfyUI Provider Adapter for Google Colab (Tesla T4) & remote workers.
    """
    id = "comfyui"
    display_name = "ComfyUI (Google Colab T4)"
    capabilities = [ProviderCapability.IMAGE, ProviderCapability.VIDEO]
    is_local = False

    def is_configured(self) -> bool:
        """Returns True if there is a READY or active remote worker."""
        active = worker_registry.get_active_worker()
        return bool(active and active.get("status") == WorkerStatus.READY.value)

    def get_account_info(self) -> str:
        active = worker_registry.get_active_worker()
        if active and active.get("status") == WorkerStatus.READY.value:
            gpu = active.get("gpu_name", "Tesla T4")
            vram = active.get("vram_gb", 16.0)
            return f"Google Colab ({gpu} {vram}GB)"
        return "Colab Worker Offline"

    async def health_check(self) -> Tuple[ProviderStatus, float, str]:
        """Probes ComfyUI health on the active worker."""
        t0 = time.monotonic()
        active = worker_registry.get_active_worker()
        if not active:
            return (ProviderStatus.UNAVAILABLE, 0.0, "No active worker registered")

        probe_res = await comfy_health_probe.verify_and_update_worker(active["worker_id"])
        latency = round((time.monotonic() - t0) * 1000, 1)

        if probe_res.get("status") == "ready":
            return (ProviderStatus.AVAILABLE, latency, self.get_account_info())
        else:
            return (ProviderStatus.UNAVAILABLE, latency, probe_res.get("error", "Unreachable"))

    async def get_models(self) -> List[Dict[str, Any]]:
        """Returns models supported by the active ComfyUI worker."""
        active = worker_registry.get_active_worker()
        models = []
        model_names = active.get("models", ["flux2_klein", "sd15_base", "wan22_i2v"]) if active else ["flux2_klein", "sd15_base"]
        for m in model_names:
            models.append({
                "id": m,
                "name": f"ComfyUI / {m.replace('_', ' ').title()}",
                "free": True,
                "local": False,
                "status": "available" if self.is_configured() else "offline"
            })
        return models

    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Executes workflow-first image generation on ComfyUI (Tesla T4) via CreativeEngine.
        Vaults media output and returns HMAC signed URLs.
        """
        t0 = time.monotonic()
        active_worker = worker_registry.get_active_worker()
        if not active_worker or active_worker.get("status") != WorkerStatus.READY.value:
            raise RuntimeError("ComfyUI remote worker (Google Colab) is OFFLINE. Fallback triggered.")

        workflow_template = kwargs.get("workflow") or kwargs.get("template") or "flux2_klein_txt2img"
        parameters = kwargs.copy()

        log.info(f"[ComfyUIProvider] Executing '{workflow_template}' on worker '{active_worker['worker_id']}' for prompt: '{prompt[:40]}...'")

        # 1. Dispatch workflow via CreativeEngine
        exec_res = await creative_engine.run_workflow(
            template_name_or_path=workflow_template,
            prompt=prompt,
            parameters=parameters,
            negative_prompt=kwargs.get("negative_prompt"),
            seed=kwargs.get("seed")
        )

        if exec_res.get("status") not in ("SUBMITTED", "COMPLETED"):
            err = exec_res.get("error", "Workflow submission failed")
            raise RuntimeError(f"ComfyUI execution error: {err}")

        job_id = exec_res.get("job_id")

        # 2. Wait for completion & Auto-Vault output
        # If not reused, poll until complete or timeout
        poll_start = time.time()
        timeout_sec = float(kwargs.get("timeout", 180.0))
        vault_res = {"status": "FAILED"}

        while (time.time() - poll_start) < timeout_sec:
            status_info = await creative_engine.download_and_vault_artifact(job_id)
            if status_info.get("status") == "COMPLETED":
                vault_res = status_info
                break
            import asyncio
            await asyncio.sleep(2.5)

        if vault_res.get("status") != "COMPLETED":
            raise RuntimeError(f"ComfyUI generation timed out or failed to vault asset for job '{job_id}'")

        duration_ms = round((time.monotonic() - t0) * 1000, 1)

        # 3. Generate HMAC Presigned Streaming URLs
        signed = generate_signed_urls(job_id=job_id, ttl=1800)
        view_url = signed.get("view_url", "")
        download_url = signed.get("download_url", "")

        gpu_name = active_worker.get("gpu_name", "NVIDIA Tesla T4")
        session_id = active_worker.get("session_id", "colab-session")
        model_name = kwargs.get("model", "FLUX.2 Klein 4B")

        # Record in provider_history.db with true telemetry
        provider_history.record(
            provider="comfyui",
            capability="image",
            prompt=prompt,
            model=model_name,
            account=f"Google Colab ({gpu_name})",
            result_url=view_url,
            duration_ms=duration_ms,
            status="ok"
        )

        content_msg = (
            f"🖼️ **Imagen generada por ComfyUI (Google Colab / {gpu_name} 16GB):**\n\n"
            f"![Imagen]({view_url})\n\n"
            f"[📥 Descargar Imagen]({download_url}) [🌐 Ver HD]({view_url})"
        )

        return {
            "status": "success",
            "provider": "comfyui",
            "backend": "google-colab",
            "worker_id": active_worker["worker_id"],
            "session_id": session_id,
            "gpu": gpu_name,
            "model": model_name,
            "workflow": workflow_template,
            "job_id": job_id,
            "image_url": view_url,
            "download_url": download_url,
            "latency_ms": duration_ms,
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": content_msg
                }
            }],
            "_provider_used": "comfyui",
            "_backend_used": "google-colab",
            "_gpu_used": gpu_name
        }

    async def generate_video(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Executes video generation on ComfyUI (Tesla T4) via CreativeEngine.
        """
        t0 = time.monotonic()
        active_worker = worker_registry.get_active_worker()
        if not active_worker or active_worker.get("status") != WorkerStatus.READY.value:
            raise RuntimeError("ComfyUI remote worker is OFFLINE. Fallback triggered.")

        workflow_template = kwargs.get("workflow") or "wan22_i2v"
        parameters = kwargs.copy()

        exec_res = await creative_engine.run_workflow(
            template_name_or_path=workflow_template,
            prompt=prompt,
            parameters=parameters
        )

        job_id = exec_res.get("job_id")
        poll_start = time.time()
        timeout_sec = float(kwargs.get("timeout", 300.0))
        vault_res = {"status": "FAILED"}

        while (time.time() - poll_start) < timeout_sec:
            status_info = await creative_engine.download_and_vault_artifact(job_id)
            if status_info.get("status") == "COMPLETED":
                vault_res = status_info
                break
            import asyncio
            await asyncio.sleep(3.0)

        if vault_res.get("status") != "COMPLETED":
            raise RuntimeError(f"ComfyUI video generation timed out for job '{job_id}'")

        duration_ms = round((time.monotonic() - t0) * 1000, 1)
        signed = generate_signed_urls(job_id=job_id, ttl=1800)
        view_url = signed.get("view_url", "")
        download_url = signed.get("download_url", "")
        gpu_name = active_worker.get("gpu_name", "NVIDIA Tesla T4")

        provider_history.record(
            provider="comfyui",
            capability="video",
            prompt=prompt,
            model="Wan 2.2",
            account=f"Google Colab ({gpu_name})",
            result_url=view_url,
            duration_ms=duration_ms,
            status="ok"
        )

        content_msg = (
            f"🎬 **Video generado por ComfyUI (Google Colab / {gpu_name} 16GB):**\n\n"
            f"![Video]({view_url})\n\n"
            f"[📥 Descargar Video]({download_url}) [🌐 Ver Resultado]({view_url})"
        )

        return {
            "status": "success",
            "provider": "comfyui",
            "backend": "google-colab",
            "worker_id": active_worker["worker_id"],
            "gpu": gpu_name,
            "job_id": job_id,
            "video_url": view_url,
            "download_url": download_url,
            "latency_ms": duration_ms,
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": content_msg
                }
            }],
            "_provider_used": "comfyui",
            "_backend_used": "google-colab",
            "_gpu_used": gpu_name
        }


comfyui_provider_adapter = ComfyUIProviderAdapter()
