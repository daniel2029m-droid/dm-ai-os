"""
Integration Tests for Remote ComfyUI (Google Colab Tesla T4) & AI Router (DM AI OS v1.5.1)
===========================================================================================
"""

import time
import pytest
from starlette.testclient import TestClient

from src.api.server import app
from src.providers.worker_registry import worker_registry, WorkerStatus
from src.adapters.comfy_adapter import comfy_adapter
from src.providers.provider_manager import provider_manager
from src.core.creative_engine import creative_engine


@pytest.fixture
def client():
    return TestClient(app)


def test_ssrf_protection_on_worker_registration(client):
    # Try internal AWS/GCP metadata IP
    payload = {
        "worker_id": "malicious-worker",
        "session_id": "rt-1",
        "backend": "google-colab",
        "provider": "comfyui",
        "endpoint": "http://169.254.169.254/latest/meta-data/",
        "gpu_name": "Tesla T4",
        "vram_gb": 16.0
    }
    r = client.post("/api/v1/workers/register", json=payload)
    assert r.status_code == 400
    assert "Disallowed internal host" in r.text or "SSRF" in r.text or "Invalid" in r.text


def test_worker_registration_and_status_api(client, monkeypatch):
    # Mock probe endpoint to return healthy T4
    from src.core.comfy_health_probe import comfy_health_probe

    async def mock_probe(url):
        return True, {"gpu_name": "Tesla T4", "vram_total_gb": 15.0, "latency_ms": 30.0}, None

    monkeypatch.setattr(comfy_health_probe, "probe_endpoint", mock_probe)

    payload = {
        "worker_id": "colab-comfy-test-01",
        "session_id": "session-t4-2026",
        "backend": "google-colab",
        "provider": "comfyui",
        "endpoint": "https://test-colab-tunnel.trycloudflare.com",
        "gpu_name": "NVIDIA Tesla T4",
        "vram_gb": 16.0
    }
    r = client.post("/api/v1/workers/register", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "SUCCESS"

    # Verify status endpoint
    r_stat = client.get("/api/v1/workers/status")
    assert r_stat.status_code == 200
    stat_data = r_stat.json()
    assert stat_data["status"] == "ready"
    assert stat_data["gpu_name"] == "NVIDIA Tesla T4"

    # Verify ComfyAdapter resolved active endpoint
    active_ep = comfy_adapter.get_active_endpoint()
    assert active_ep == "https://test-colab-tunnel.trycloudflare.com"


def test_worker_heartbeat_api(client):
    r_hb = client.post("/api/v1/workers/heartbeat", json={
        "worker_id": "colab-comfy-test-01",
        "session_id": "session-t4-2026"
    })
    assert r_hb.status_code == 200
    assert r_hb.json()["status"] == "OK"


@pytest.mark.asyncio
async def test_comfyui_provider_image_generation(monkeypatch):
    # Setup ready worker
    worker_registry.register_worker(
        worker_id="colab-comfy-primary",
        session_id="session-t4-prod",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://colab-worker.trycloudflare.com",
        gpu_name="NVIDIA Tesla T4",
        vram_gb=16.0,
        status="ready"
    )

    # Mock ComfyUI prompt submission & download
    async def mock_run_workflow(template_name_or_path, prompt, parameters=None, negative_prompt=None, seed=None):
        return {
            "status": "COMPLETED",
            "job_id": "test_job_t4_001",
            "backend": "COLAB_COMFYUI",
            "manifest": {"prompt": prompt}
        }

    async def mock_download_and_vault(job_id):
        return {
            "status": "COMPLETED",
            "job_id": job_id,
            "output_assets": ["Artifacts/media/test_job_t4_001/output.png"]
        }

    monkeypatch.setattr(creative_engine, "run_workflow", mock_run_workflow)
    monkeypatch.setattr(creative_engine, "download_and_vault_artifact", mock_download_and_vault)

    # Route through provider manager with AUTO mode
    res = await provider_manager.route_image(
        prompt="Genera un retrato fotorealista de una mujer en alta definicion",
        preferred_provider="comfyui"
    )

    assert res["status"] == "success"
    assert res["provider"] == "comfyui"
    assert res["backend"] == "google-colab"
    assert res["gpu"] == "NVIDIA Tesla T4"
    assert res["_provider_used"] == "comfyui"
    assert "Tesla T4" in res["choices"][0]["message"]["content"]
    assert "/api/v1/creative/assets/test_job_t4_001/view" in res["image_url"]


@pytest.mark.asyncio
async def test_fallback_to_nvidia_when_colab_offline(monkeypatch):
    # Mark worker as offline
    worker_registry.register_worker(
        worker_id="colab-comfy-primary",
        session_id="session-t4-prod",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://dead-tunnel.trycloudflare.com",
        gpu_name="Tesla T4",
        vram_gb=16.0,
        status="offline"
    )

    # Mock NVIDIA adapter to succeed
    from src.adapters.nvidia_adapter import nvidia_adapter

    async def mock_nvidia_gen(prompt, **kwargs):
        return {
            "status": "success",
            "provider": "nvidia",
            "model": "black-forest-labs/flux.2-klein-4b",
            "image_url": "/api/providers/uploads/nvidia_test.png",
            "latency_ms": 3200.0,
            "choices": [{"message": {"role": "assistant", "content": "NVIDIA NIM Result"}}]
        }

    monkeypatch.setattr(nvidia_adapter, "generate_image", mock_nvidia_gen)

    # Route in AUTO mode
    res = await provider_manager.route_image(
        prompt="Genera una flor hermosa",
        preferred_provider="auto"
    )

    # Must transparently report nvidia provider
    assert res["_provider_used"] == "nvidia"
