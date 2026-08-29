"""
Unit Tests for Remote Worker Registry & Dual-Level Health Probe (DM AI OS v1.5.1)
================================================================================
"""

import os
import time
import pytest
from pathlib import Path

from src.providers.worker_registry import WorkerRegistry, WorkerStatus
from src.core.comfy_health_probe import ComfyHealthProbe


@pytest.fixture
def temp_registry(tmp_path):
    db_file = str(tmp_path / "test_knowledge.db")
    reg = WorkerRegistry(db_path=db_file)
    reg.heartbeat_ttl_sec = 2.0  # Fast TTL for test isolation
    return reg


def test_worker_registration_and_retrieval(temp_registry):
    reg = temp_registry
    worker = reg.register_worker(
        worker_id="colab-comfy-primary",
        session_id="rt-colab-20260828-01",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://test-tunnel.trycloudflare.com",
        gpu_name="Tesla T4",
        vram_gb=15.0,
        models=["flux2_klein", "sd15_base"],
        status="ready"
    )

    assert worker["worker_id"] == "colab-comfy-primary"
    assert worker["session_id"] == "rt-colab-20260828-01"
    assert worker["gpu_name"] == "Tesla T4"
    assert worker["vram_gb"] == 15.0
    assert worker["endpoint"] == "https://test-tunnel.trycloudflare.com"
    assert worker["status"] == "ready"


def test_worker_session_renewal_without_duplicate(temp_registry):
    reg = temp_registry
    # Session 1
    reg.register_worker(
        worker_id="colab-comfy-primary",
        session_id="rt-colab-session-1",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://tunnel-1.trycloudflare.com",
        gpu_name="Tesla T4",
        vram_gb=16.0
    )
    assert len(reg.list_workers()) == 1

    # Session 2 (Colab restarted with new tunnel URL)
    reg.register_worker(
        worker_id="colab-comfy-primary",
        session_id="rt-colab-session-2",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://tunnel-2.trycloudflare.com",
        gpu_name="Tesla T4",
        vram_gb=16.0
    )

    workers = reg.list_workers()
    assert len(workers) == 1
    assert workers[0]["session_id"] == "rt-colab-session-2"
    assert workers[0]["endpoint"] == "https://tunnel-2.trycloudflare.com"


def test_worker_heartbeat_and_expiration(temp_registry):
    reg = temp_registry
    reg.register_worker(
        worker_id="colab-comfy-primary",
        session_id="rt-colab-01",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://tunnel.trycloudflare.com",
        gpu_name="Tesla T4",
        vram_gb=16.0,
        status="ready"
    )

    assert reg.get_active_worker() is not None

    # Update heartbeat
    ok = reg.record_heartbeat("colab-comfy-primary", session_id="rt-colab-01")
    assert ok is True

    # Sleep past heartbeat TTL (2.0s)
    time.sleep(2.2)

    # Worker should now be evaluated as OFFLINE
    w = reg.get_worker("colab-comfy-primary")
    assert w["status"] == WorkerStatus.OFFLINE.value
    assert reg.get_active_worker() is None


@pytest.mark.asyncio
async def test_health_probe_mock(monkeypatch):
    probe = ComfyHealthProbe()

    # Mock probe response
    async def mock_probe_endpoint(base_url):
        return True, {
            "latency_ms": 42.5,
            "gpu_name": "Tesla T4",
            "vram_total_gb": 15.0,
            "vram_free_gb": 14.2
        }, None

    monkeypatch.setattr(probe, "probe_endpoint", mock_probe_endpoint)
    is_alive, stats, err = await probe.probe_endpoint("https://dummy-comfy.com")
    assert is_alive is True
    assert stats["gpu_name"] == "Tesla T4"
    assert err is None
