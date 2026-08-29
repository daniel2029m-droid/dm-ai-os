"""
Comprehensive Test Suite for Compute Plane Orchestrator & Legitimate Colab Activation (DM AI OS v1.5.1)
========================================================================================================
"""

import time
import pytest
from starlette.testclient import TestClient

from src.api.server import app
from src.core.compute_plane_orchestrator import compute_plane_orchestrator, ComputeState
from src.providers.worker_registry import worker_registry, WorkerStatus
from src.core.comfy_health_probe import comfy_health_probe
from src.providers.provider_manager import provider_manager
from src.core.creative_engine import creative_engine


@pytest.fixture
def client():
    return TestClient(app)


def test_compute_plane_ready():
    # Register ready worker
    worker_registry.register_worker(
        worker_id="colab-comfy-primary",
        session_id="session-t4-ready",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://live-tunnel.trycloudflare.com",
        gpu_name="Tesla T4",
        vram_gb=15.0,
        status="ready"
    )

    status = compute_plane_orchestrator.get_compute_status()
    assert status["state"] == ComputeState.READY.value
    assert status["status"] == "ready"
    assert status["gpu_name"] == "Tesla T4"
    assert status["requires_activation"] is False


def test_compute_plane_requires_activation():
    # Mark worker offline
    worker_registry.register_worker(
        worker_id="colab-comfy-primary",
        session_id="session-t4-dead",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://dead-tunnel.trycloudflare.com",
        gpu_name="Tesla T4",
        vram_gb=15.0,
        status="offline"
    )

    status = compute_plane_orchestrator.get_compute_status()
    assert status["state"] == ComputeState.REQUIRES_ACTIVATION.value
    assert status["requires_activation"] is True
    assert "colab.research.google.com" in status["activation_url"]


def test_compute_plane_activation_api_endpoint(client):
    r = client.get("/api/v1/workers/activate")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "OK"
    assert "colab.research.google.com" in data["activation_url"]


def test_worker_session_renewal_and_tunnel_rotation():
    # Worker starts on session 1
    worker_registry.register_worker(
        worker_id="colab-comfy-primary",
        session_id="rt-session-001",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://tunnel-a.trycloudflare.com",
        gpu_name="Tesla T4",
        vram_gb=16.0,
        status="ready"
    )
    assert worker_registry.get_active_worker()["endpoint"] == "https://tunnel-a.trycloudflare.com"

    # Colab restarts with new session and new tunnel URL
    worker_registry.register_worker(
        worker_id="colab-comfy-primary",
        session_id="rt-session-002",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://tunnel-b.trycloudflare.com",
        gpu_name="Tesla T4",
        vram_gb=16.0,
        status="ready"
    )
    active = worker_registry.get_active_worker()
    assert active["session_id"] == "rt-session-002"
    assert active["endpoint"] == "https://tunnel-b.trycloudflare.com"


@pytest.mark.asyncio
async def test_gpu_and_comfy_health_verification(monkeypatch):
    # Mock health probe to verify GPU detection
    async def mock_probe(url):
        return True, {
            "gpu_name": "NVIDIA Tesla T4",
            "vram_total_gb": 15.0,
            "vram_free_gb": 14.1,
            "latency_ms": 35.0
        }, None

    monkeypatch.setattr(comfy_health_probe, "probe_endpoint", mock_probe)

    worker_registry.register_worker(
        worker_id="colab-comfy-primary",
        session_id="session-t4-probe",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://mock-tunnel.trycloudflare.com",
        gpu_name="Tesla T4",
        vram_gb=16.0
    )

    probe_res = await comfy_health_probe.verify_and_update_worker("colab-comfy-primary")
    assert probe_res["status"] == "ready"
    assert probe_res["gpu_name"] == "NVIDIA Tesla T4"


def test_no_false_ready_state():
    # If heartbeat expires, worker must not return ready
    worker_registry.register_worker(
        worker_id="colab-comfy-primary",
        session_id="session-expired",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://expired-tunnel.trycloudflare.com",
        gpu_name="Tesla T4",
        vram_gb=16.0,
        status="ready"
    )

    # Artificially age the heartbeat
    worker_registry.heartbeat_ttl_sec = 0.1
    time.sleep(0.2)

    status = compute_plane_orchestrator.get_compute_status()
    assert status["state"] != ComputeState.READY.value
    assert status["requires_activation"] is True


@pytest.mark.asyncio
async def test_explicit_comfyui_does_not_silent_fallback(monkeypatch):
    # Worker is offline
    worker_registry.register_worker(
        worker_id="colab-comfy-primary",
        session_id="session-dead",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://dead.trycloudflare.com",
        gpu_name="Tesla T4",
        vram_gb=16.0,
        status="offline"
    )

    # When user explicitly selects comfyui, it must raise/fail rather than quietly calling NVIDIA NIM
    with pytest.raises(RuntimeError) as exc_info:
        await provider_manager.route_image(
            prompt="Genera una imagen con ComfyUI exclusivamente",
            preferred_provider="comfyui"
        )
    assert "OFFLINE" in str(exc_info.value) or "Fallback triggered" in str(exc_info.value)


@pytest.mark.asyncio
async def test_auto_mode_fallback_when_offline(monkeypatch):
    # Worker is offline
    worker_registry.register_worker(
        worker_id="colab-comfy-primary",
        session_id="session-dead",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://dead.trycloudflare.com",
        gpu_name="Tesla T4",
        vram_gb=16.0,
        status="offline"
    )

    from src.adapters.nvidia_adapter import nvidia_adapter

    async def mock_nvidia(prompt, **kwargs):
        return {
            "status": "success",
            "provider": "nvidia",
            "model": "black-forest-labs/flux.2-klein-4b",
            "image_url": "/api/providers/uploads/nvidia_auto.png",
            "choices": [{"message": {"role": "assistant", "content": "NVIDIA Output"}}]
        }

    monkeypatch.setattr(nvidia_adapter, "generate_image", mock_nvidia)

    # In AUTO mode, it falls back to NVIDIA and truthfully labels provider as nvidia
    res = await provider_manager.route_image(
        prompt="Genera una rosa roja en modo auto",
        preferred_provider="auto"
    )
    assert res["_provider_used"] == "nvidia"


@pytest.mark.asyncio
async def test_generation_after_recovery(monkeypatch):
    # Simulate recovery: worker comes back online
    worker_registry.heartbeat_ttl_sec = 90.0
    worker_registry.register_worker(
        worker_id="colab-comfy-primary",
        session_id="session-recovered",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://recovered.trycloudflare.com",
        gpu_name="NVIDIA Tesla T4",
        vram_gb=15.0,
        status="ready"
    )

    async def mock_run_wf(*args, **kwargs):
        return {"status": "COMPLETED", "job_id": "job_recov_001", "backend": "COLAB_COMFYUI"}

    async def mock_vault(*args, **kwargs):
        return {"status": "COMPLETED", "job_id": "job_recov_001", "output_assets": ["Artifacts/media/recov.png"]}

    monkeypatch.setattr(creative_engine, "run_workflow", mock_run_wf)
    monkeypatch.setattr(creative_engine, "download_and_vault_artifact", mock_vault)

    res = await provider_manager.route_image(
        prompt="Genera imagen tras recuperacion",
        preferred_provider="auto"
    )

    # Immediately prioritizes ComfyUI
    assert res["_provider_used"] == "comfyui"
    assert res["gpu"] == "NVIDIA Tesla T4"
    assert res["backend"] == "google-colab"
