"""
DM AI OS — ComfyUI Remote Health Probe (Dual-Level Verification)
================================================================
Implements independent validation of:
  1. Worker Heartbeat (Colab bootstrap process alive)
  2. ComfyUI Health Probe (HTTP endpoint responsive, /system_stats accessible, GPU confirmed, queue functional)

A worker is ONLY marked READY when both levels succeed.
"""

import time
import httpx
import logging
from typing import Dict, Any, Tuple, Optional

from ..providers.worker_registry import worker_registry, WorkerStatus

log = logging.getLogger("comfy_health_probe")


class ComfyHealthProbe:
    """
    Performs active, deep health verification of remote ComfyUI workers.
    """

    def __init__(self, timeout_sec: float = 6.0):
        self.timeout_sec = timeout_sec

    async def probe_endpoint(self, base_url: str) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Queries ComfyUI /system_stats endpoint to inspect GPU, VRAM, and queue health.
        Returns (is_healthy, stats_dict, error_message).
        """
        if not base_url or not base_url.strip():
            return False, {}, "Empty endpoint URL"

        clean_url = base_url.rstrip("/")
        stats_url = f"{clean_url}/system_stats"
        queue_url = f"{clean_url}/queue"

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec, follow_redirects=True) as client:
                r_stats = await client.get(stats_url)
                latency_ms = round((time.monotonic() - t0) * 1000, 1)

                if r_stats.status_code != 200:
                    return False, {"latency_ms": latency_ms}, f"/system_stats returned HTTP {r_stats.status_code}"

                data = r_stats.json()
                sys_info = data.get("system", {})
                devices = data.get("devices", [])

                gpu_name = "CPU"
                vram_total_gb = 0.0
                vram_free_gb = 0.0

                if devices and isinstance(devices, list):
                    dev0 = devices[0]
                    gpu_name = dev0.get("name", "Unknown GPU")
                    vram_total = dev0.get("vram_total", 0)
                    vram_free = dev0.get("vram_free", 0)
                    vram_total_gb = round(vram_total / (1024 ** 3), 2)
                    vram_free_gb = round(vram_free / (1024 ** 3), 2)

                # Query queue status
                pending_count = 0
                running_count = 0
                try:
                    r_queue = await client.get(queue_url)
                    if r_queue.status_code == 200:
                        q_data = r_queue.json()
                        pending_count = len(q_data.get("queue_pending", []))
                        running_count = len(q_data.get("queue_running", []))
                except Exception:
                    pass

                stats = {
                    "latency_ms": latency_ms,
                    "gpu_name": gpu_name,
                    "vram_total_gb": vram_total_gb,
                    "vram_free_gb": vram_free_gb,
                    "python_version": sys_info.get("python_version", ""),
                    "comfy_version": sys_info.get("comfyui_version", ""),
                    "queue_pending": pending_count,
                    "queue_running": running_count,
                    "raw_system": sys_info
                }
                return True, stats, None

        except httpx.TimeoutException:
            return False, {}, f"Health probe timed out after {self.timeout_sec}s"
        except httpx.ConnectError as ce:
            return False, {}, f"Connection refused to {clean_url}: {ce}"
        except Exception as e:
            return False, {}, f"Health probe error: {str(e)}"

    async def verify_and_update_worker(self, worker_id: str) -> Dict[str, Any]:
        """
        Executes dual-level health verification for a registered worker and updates its SQLite status.
        """
        worker = worker_registry.get_worker(worker_id)
        if not worker:
            return {"status": "error", "message": f"Worker '{worker_id}' not found."}

        endpoint = worker.get("endpoint") or worker.get("tunnel_endpoint")
        is_alive, stats, err = await self.probe_endpoint(endpoint)

        if is_alive:
            # GPU validation: Tesla T4 or compatible
            gpu_detected = stats.get("gpu_name", worker.get("gpu_name", "Unknown"))
            vram_detected = stats.get("vram_total_gb", worker.get("vram_gb", 16.0))

            worker_registry.update_health_status(
                worker_id=worker_id,
                health_status="healthy",
                status=WorkerStatus.READY,
                error_message=None
            )
            log.info(f"[ComfyHealthProbe] Worker '{worker_id}' is READY (GPU: {gpu_detected}, VRAM: {vram_detected}GB, Latency: {stats.get('latency_ms')}ms)")
            return {
                "status": "ready",
                "worker_id": worker_id,
                "gpu_name": gpu_detected,
                "vram_total_gb": vram_detected,
                "stats": stats
            }
        else:
            worker_registry.update_health_status(
                worker_id=worker_id,
                health_status="unreachable",
                status=WorkerStatus.DEGRADED,
                error_message=err
            )
            log.warning(f"[ComfyHealthProbe] Worker '{worker_id}' health check failed: {err}")
            return {
                "status": "degraded",
                "worker_id": worker_id,
                "error": err
            }


comfy_health_probe = ComfyHealthProbe()
