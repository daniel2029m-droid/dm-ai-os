"""
DM AI OS v1.5.1 — Model Storage Plane Diagnostic Router
========================================================
Provides inspectable telemetry for Model Storage Plane,
multi-account storage status, and capability matrix.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..core.model_storage_plane import model_storage_plane
from ..providers.worker_registry import worker_registry

model_storage_router = APIRouter(prefix="/api/v1", tags=["Model Storage Plane"])


@model_storage_router.get("/models")
async def list_all_models():
    """
    Returns declarative model catalog, multi-component specifications,
    and availability matrix against active Compute Worker.
    """
    active_worker = worker_registry.get_active_worker()
    avail_vram = active_worker.get("vram_gb") if active_worker else None
    
    matrix = model_storage_plane.evaluate_all_models(available_vram_gb=avail_vram)
    return JSONResponse(content={
        "status": "OK",
        "models": matrix,
        "ready_models": [mid for mid, info in matrix.items() if info.get("available")],
        "active_worker_id": active_worker.get("worker_id") if active_worker else None
    })


@model_storage_router.get("/models/{model_id}")
async def get_model_status(model_id: str):
    """
    Returns detailed 3-level resolution and component breakdown for a single model.
    """
    active_worker = worker_registry.get_active_worker()
    avail_vram = active_worker.get("vram_gb") if active_worker else None

    res = model_storage_plane.resolve_model(model_id, available_vram_gb=avail_vram)
    if res.get("status") == "NOT_REGISTERED":
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found in catalog.")
    
    return JSONResponse(content={"status": "OK", "model": res})


@model_storage_router.get("/model-storage/status")
async def get_storage_plane_status():
    """
    Returns status of all registered persistent storage volumes (Google Drive, Shared Drives).
    """
    storages = model_storage_plane.list_storages()
    active_worker = worker_registry.get_active_worker()
    avail_vram = active_worker.get("vram_gb") if active_worker else None
    matrix = model_storage_plane.evaluate_all_models(available_vram_gb=avail_vram)

    return JSONResponse(content={
        "status": "OK",
        "storages": storages,
        "storage_count": len(storages),
        "mounted_count": sum(1 for s in storages if s.get("is_mounted")),
        "model_availability": {mid: info.get("status") for mid, info in matrix.items()}
    })
