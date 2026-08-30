"""
ComfyAdapter — Dynamic Client Adapter for ComfyUI APIs (Google Colab, RunPod, Cloud & Local).
=============================================================================================
Dynamically queries WorkerRegistry for the active, healthy remote ComfyUI worker.
Provides seamless execution across Google Colab Tesla T4, RunPod, or local instances without hardcoded URLs.
"""
import os
import json
import logging
import httpx
from typing import Dict, Any, Optional, List

from ..providers.worker_registry import worker_registry, WorkerStatus

log = logging.getLogger("comfy_adapter")


class ComfyAdapter:
    def __init__(self):
        self.cloud_url = os.getenv("COMFY_CLOUD_MCP_URL", "https://cloud.comfy.org/mcp")
        self.api_key = os.getenv("COMFY_API_KEY", "")
        self.runpod_url = os.getenv("COMFYUI_REMOTE_URL", "")
        self.local_url = os.getenv("COMFYUI_LOCAL_URL", "http://127.0.0.1:8188")
        self.local_enabled = os.getenv("COMFYUI_LOCAL_ENABLED", "false").lower() == "true"
        self.preferred_backend = os.getenv("COMFY_PREFERRED_BACKEND", "colab").lower()

    def get_active_endpoint(self) -> Optional[str]:
        """
        Resolves active ComfyUI endpoint dynamically:
        1. Checks WorkerRegistry for READY remote worker (e.g. Google Colab Tesla T4).
        2. Checks RunPod remote URL.
        3. Checks Local ComfyUI (if enabled & pingable).
        """
        # 1. Google Colab / Remote Worker Registry
        active_worker = worker_registry.get_active_worker()
        if active_worker and active_worker.get("status") == WorkerStatus.READY.value:
            endpoint = active_worker.get("endpoint") or active_worker.get("tunnel_endpoint")
            if endpoint:
                return endpoint.rstrip("/")

        # 2. RunPod URL
        if self.runpod_url:
            return self.runpod_url.rstrip("/")

        # 3. Local ComfyUI
        if self.local_enabled and self._ping_local():
            return self.local_url.rstrip("/")

        return None

    def is_available(self) -> bool:
        """Determines availability safely without crashing."""
        active_ep = self.get_active_endpoint()
        if active_ep:
            return True
        if self.preferred_backend == "cloud" and bool(self.api_key):
            return True
        return False

    def _ping_local(self) -> bool:
        try:
            with httpx.Client(timeout=1.5) as client:
                r = client.get(f"{self.local_url}/system_stats")
                return r.status_code == 200
        except Exception:
            return False

    def get_backend_info(self) -> Dict[str, Any]:
        """Returns safe telemetry about configured Comfy backends."""
        active_worker = worker_registry.get_active_worker()
        active_ep = self.get_active_endpoint()
        return {
            "available": self.is_available(),
            "active_endpoint": active_ep,
            "active_worker": active_worker,
            "preferred_backend": self.preferred_backend,
            "colab_ready": bool(active_worker and active_worker.get("status") == WorkerStatus.READY.value),
            "cloud_configured": bool(self.api_key),
            "runpod_configured": bool(self.runpod_url),
            "local_enabled": self.local_enabled,
            "local_online": self._ping_local() if self.local_enabled else False
        }

    async def submit_workflow(
        self,
        workflow_json: Dict[str, Any],
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Submits a ComfyUI workflow graph and returns job status and output information."""
        active_worker = worker_registry.get_active_worker()
        active_ep = self.get_active_endpoint()

        # 1. Remote Worker (Google Colab Tesla T4) or Direct Remote ComfyUI
        if active_ep:
            backend_label = "COLAB_COMFYUI" if (active_worker and active_worker.get("backend") == "google-colab") else "REMOTE_COMFYUI"
            gpu_name = active_worker.get("gpu_name", "Tesla T4") if active_worker else "Unknown GPU"
            worker_id = active_worker.get("worker_id", "remote-worker") if active_worker else "direct"
            session_id = active_worker.get("session_id", "session-default") if active_worker else "direct"

            try:
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                    payload = {"prompt": workflow_json}
                    res = await client.post(f"{active_ep}/prompt", json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        prompt_id = data.get("prompt_id")
                        log.info(f"[ComfyAdapter] Submitted workflow to {backend_label} at {active_ep} -> prompt_id: {prompt_id}")
                        return {
                            "status": "SUBMITTED",
                            "job_id": prompt_id,
                            "number": data.get("number"),
                            "backend": backend_label,
                            "worker_id": worker_id,
                            "session_id": session_id,
                            "gpu_name": gpu_name,
                            "endpoint": active_ep
                        }
                    return {"status": "FAILED", "code": res.status_code, "error": res.text}
            except Exception as e:
                log.error(f"[ComfyAdapter] Submission error to {active_ep}: {e}")
                # If active worker failed, trigger health probe to reflect state
                if active_worker:
                    worker_registry.update_health_status(
                        worker_id=worker_id,
                        health_status="submission_error",
                        status=WorkerStatus.DEGRADED,
                        error_message=str(e)
                    )
                return {"status": "FAILED", "error": str(e)}

        # 2. Comfy Cloud MCP / REST Backend
        if self.preferred_backend == "cloud" and self.api_key:
            headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    res = await client.post(
                        f"{self.cloud_url}/submit_workflow",
                        headers=headers,
                        json={"workflow": workflow_json, "parameters": parameters or {}}
                    )
                    if res.status_code in (200, 201):
                        return res.json()
                    return {"status": "FAILED", "code": res.status_code, "error": res.text}
            except Exception as e:
                log.error(f"[ComfyAdapter] Cloud submission error: {e}")
                return {"status": "FAILED", "error": str(e)}

        return {
            "status": "UNAVAILABLE",
            "error": "No active ComfyUI worker available (Google Colab worker offline)."
        }

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Polls execution status of a submitted workflow."""
        active_ep = self.get_active_endpoint()
        if not active_ep:
            return {"status": "UNAVAILABLE", "error": "Backend offline"}

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                res = await client.get(f"{active_ep}/history/{job_id}")
                if res.status_code == 200:
                    data = res.json()
                    if job_id in data:
                        return {"status": "COMPLETED", "history": data[job_id]}
                    return {"status": "RUNNING", "job_id": job_id}
                return {"status": "RUNNING", "job_id": job_id}
        except Exception as e:
            return {"status": "FAILED", "error": str(e)}

    async def get_job_outputs(self, job_id: str) -> List[Dict[str, Any]]:
        """Inspects /history/{job_id} and extracts all generated media output items."""
        status_res = await self.get_job_status(job_id)
        if status_res.get("status") != "COMPLETED":
            return []

        history = status_res.get("history", {})
        outputs_map = history.get("outputs", {})
        items = []
        for node_id, node_out in outputs_map.items():
            if isinstance(node_out, dict):
                # Images
                for img in node_out.get("images", []):
                    items.append({
                        "node_id": node_id,
                        "filename": img.get("filename"),
                        "subfolder": img.get("subfolder", ""),
                        "type": img.get("type", "output")
                    })
                # Animated WEBP / Video formats
                for anim in node_out.get("gifs", []):
                    items.append({
                        "node_id": node_id,
                        "filename": anim.get("filename"),
                        "subfolder": anim.get("subfolder", ""),
                        "type": anim.get("type", "output")
                    })
        return items

    async def download_output_bytes(
        self,
        filename: str,
        subfolder: str = "",
        file_type: str = "output"
    ) -> Optional[bytes]:
        """Downloads output asset bytes directly from remote ComfyUI /view endpoint."""
        active_ep = self.get_active_endpoint()
        if not active_ep:
            return None

        view_url = f"{active_ep}/view"
        params = {"filename": filename, "subfolder": subfolder, "type": file_type}
        try:
            async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
                res = await client.get(view_url, params=params)
                if res.status_code == 200:
                    return res.content
                log.warning(f"[ComfyAdapter] /view returned HTTP {res.status_code} for {filename}")
        except Exception as e:
            log.error(f"[ComfyAdapter] Error downloading {filename} via /view: {e}")
        return None

    async def get_job_output(self, job_id: str) -> Dict[str, Any]:
        """Retrieves output assets from a completed workflow."""
        outputs = await self.get_job_outputs(job_id)
        return {"status": "SUCCESS", "job_id": job_id, "outputs": outputs}

    async def upload_image(self, file_data: Any, filename: str) -> Optional[str]:
        """
        Uploads an input image (for FaceSwap, Img2Img, ControlNet) to remote ComfyUI /upload/image.
        Returns the uploaded filename on ComfyUI's input directory.
        """
        active_ep = self.get_active_endpoint()
        if not active_ep:
            return None

        if isinstance(file_data, (str, Path)):
            p = Path(file_data)
            if p.exists():
                file_bytes = p.read_bytes()
                filename = filename or p.name
            else:
                return None
        elif isinstance(file_data, bytes):
            file_bytes = file_data
        else:
            return None

        upload_url = f"{active_ep}/upload/image"
        files = {"image": (filename, file_bytes, "image/png")}
        data = {"overwrite": "true"}
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                res = await client.post(upload_url, files=files, data=data)
                if res.status_code == 200:
                    resp_json = res.json()
                    return resp_json.get("name", filename)
                log.warning(f"[ComfyAdapter] /upload/image returned HTTP {res.status_code}")
        except Exception as e:
            log.error(f"[ComfyAdapter] Error uploading image {filename}: {e}")
        return None

    async def search_templates(self, query: str = "") -> List[Dict[str, Any]]:
        """Search pre-built workflow templates."""
        return []


    async def search_models(self, query: str = "") -> List[Dict[str, Any]]:
        """Search available models in backend catalog."""
        return []


# Singleton instance
comfy_adapter = ComfyAdapter()
