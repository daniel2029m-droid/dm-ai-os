"""
DM AI OS — Remote Worker Handshake & Heartbeat Router
=====================================================
Provides authenticated endpoints for Google Colab, RunPod, and local GPU workers.
Protects against SSRF and validates worker health before admitting workers to READY status.
"""

import re
import time
import logging
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import JSONResponse

from ..providers.worker_registry import worker_registry, WorkerStatus
from ..core.comfy_health_probe import comfy_health_probe
from .auth import verify_api_key

log = logging.getLogger("workers_router")

workers_router = APIRouter(prefix="/api/v1/workers", tags=["Workers"])


# ── SSRF & URL Validation ──────────────────────────────────────

ALLOWED_SCHEMES = {"http", "https"}
DISALLOWED_HOSTS = {"169.254.169.254", "metadata.google.internal", "metadata"}

def validate_safe_endpoint(url_str: str) -> str:
    """
    Validates endpoint URL for valid scheme, hostname, and prevents common cloud metadata SSRF.
    """
    if not url_str or not url_str.strip():
        raise HTTPException(status_code=400, detail="Worker endpoint URL is required.")

    clean_url = url_str.strip()
    try:
        parsed = urlparse(clean_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid worker URL format: {e}")

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise HTTPException(status_code=400, detail=f"Scheme '{parsed.scheme}' not allowed. Must be HTTP or HTTPS.")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid worker URL: missing hostname.")

    if hostname in DISALLOWED_HOSTS:
        log.warning(f"[WorkersRouter] SSRF attempt blocked for host: {hostname}")
        raise HTTPException(status_code=400, detail="Disallowed internal host.")

    return clean_url.rstrip("/")


# ── Schemas ───────────────────────────────────────────────────

class WorkerRegisterRequest(BaseModel):
    worker_id: str = Field(..., description="Logical permanent ID (e.g. colab-comfy-primary)")
    session_id: str = Field(..., description="Runtime ephemeral session ID (e.g. rt-colab-20260828-01)")
    backend: str = Field("google-colab", description="Backend runtime provider")
    provider: str = Field("comfyui", description="Inference engine provider")
    endpoint: str = Field(..., description="Public tunnel or direct URL to ComfyUI")
    tunnel_endpoint: Optional[str] = None
    gpu_name: str = Field("Tesla T4", description="GPU model name")
    vram_gb: float = Field(16.0, description="Available GPU VRAM in GB")
    comfy_version: Optional[str] = None
    models: List[str] = Field(default_factory=lambda: ["flux2_klein", "sd15_base"])
    custom_nodes: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=lambda: ["image", "video"])
    auth_token: Optional[str] = None


class WorkerHeartbeatRequest(BaseModel):
    worker_id: str
    session_id: Optional[str] = None
    gpu_utilization_pct: Optional[float] = None
    vram_used_gb: Optional[float] = None


# ── Endpoints ─────────────────────────────────────────────────

@workers_router.post("/register")
async def register_worker(req: WorkerRegisterRequest, request: Request):
    """
    Registers or updates a remote ComfyUI compute worker (e.g. Google Colab Tesla T4).
    Validates URL safety, stores worker in persistent registry, probes health, and returns status.
    """
    clean_endpoint = validate_safe_endpoint(req.endpoint)
    tunnel_clean = validate_safe_endpoint(req.tunnel_endpoint) if req.tunnel_endpoint else clean_endpoint

    log.info(f"[WorkersRouter] Registering worker '{req.worker_id}' (Session: '{req.session_id}', GPU: '{req.gpu_name}', Endpoint: '{clean_endpoint}')")

    # Initial registration in RECONNECTING / ONLINE state
    registered = worker_registry.register_worker(
        worker_id=req.worker_id,
        session_id=req.session_id,
        backend=req.backend,
        provider=req.provider,
        endpoint=clean_endpoint,
        tunnel_endpoint=tunnel_clean,
        gpu_name=req.gpu_name,
        vram_gb=req.vram_gb,
        comfy_version=req.comfy_version,
        models=req.models,
        custom_nodes=req.custom_nodes,
        capabilities=req.capabilities,
        status=WorkerStatus.READY.value
    )

    # Immediately perform deep ComfyUI Health Probe
    probe_result = await comfy_health_probe.verify_and_update_worker(req.worker_id)

    return JSONResponse(content={
        "status": "SUCCESS",
        "message": f"Worker '{req.worker_id}' registered successfully.",
        "worker": worker_registry.get_worker(req.worker_id),
        "health_probe": probe_result
    })


@workers_router.post("/heartbeat")
async def worker_heartbeat(req: WorkerHeartbeatRequest):
    """
    Heartbeat ping from Colab bootstrap daemon.
    Updates worker heartbeat timestamp and prevents expiration.
    Automatically re-evaluates ComfyHealthProbe if worker is degraded or reconnecting.
    """
    ok = worker_registry.record_heartbeat(
        worker_id=req.worker_id,
        session_id=req.session_id,
        gpu_utilization_pct=req.gpu_utilization_pct,
        vram_used_gb=req.vram_used_gb
    )

    if not ok:
        raise HTTPException(status_code=404, detail=f"Worker '{req.worker_id}' not found. Please register first.")

    worker = worker_registry.get_worker(req.worker_id)
    if worker and worker.get("status") in (WorkerStatus.DEGRADED.value, WorkerStatus.RECONNECTING.value):
        # Auto-recover degraded worker if ComfyUI health probe now succeeds
        # Apply minimal backoff: at most once every 10s
        now = time.time()
        last_check = worker.get("last_health_check") or 0.0
        if (now - last_check) >= 10.0:
            log.info(f"[WorkersRouter] Retrying health probe for degraded worker '{req.worker_id}' on heartbeat...")
            await comfy_health_probe.verify_and_update_worker(req.worker_id)
            worker = worker_registry.get_worker(req.worker_id)

    return JSONResponse(content={
        "status": "OK",
        "worker_id": req.worker_id,
        "worker_status": worker.get("status") if worker else "unknown",
        "server_time": time.time()
    })


@workers_router.get("/status")
async def get_creative_engine_status():
    """
    Returns public health telemetry for the iPhone Mobile PWA status banner and settings.
    Includes 1-click Colab activation URL if offline.
    """
    from ..core.compute_plane_orchestrator import compute_plane_orchestrator
    status_data = compute_plane_orchestrator.get_compute_status()
    return JSONResponse(content=status_data)


@workers_router.get("/activate")
async def get_colab_activation_url():
    """
    Returns the direct 1-click Colab activation link.
    """
    from ..core.compute_plane_orchestrator import compute_plane_orchestrator
    return JSONResponse(content={
        "status": "OK",
        "activation_url": compute_plane_orchestrator.get_activation_url()
    })


@workers_router.get("/list", dependencies=[Depends(verify_api_key)])
async def list_all_workers():
    """Detailed worker listing for administrative inspectability."""
    workers = worker_registry.list_workers()
    return JSONResponse(content={"workers": workers, "count": len(workers)})
