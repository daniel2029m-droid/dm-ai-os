"""
Unit Tests for Remote Worker Registry & Dual-Level Health Probe (DM AI OS v1.5.1)
================================================================================
"""

import os
import time
import sqlite3
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


@pytest.mark.asyncio
async def test_degraded_worker_auto_recovery_on_heartbeat(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from src.api.workers_router import workers_router
    from src.core.comfy_health_probe import comfy_health_probe
    from src.providers.worker_registry import worker_registry

    # 1. Register worker
    worker_registry.register_worker(
        worker_id="colab-test-recovery",
        session_id="rt-test-01",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://test-tunnel.trycloudflare.com",
        gpu_name="Tesla T4",
        vram_gb=15.0,
        status=WorkerStatus.DEGRADED.value
    )
    # Simulate past health check so 10s cooldown is satisfied
    worker_registry.update_health_status(
        worker_id="colab-test-recovery",
        health_status="unreachable",
        status=WorkerStatus.DEGRADED,
        error_message="Initial DNS failure"
    )
    # Manually set last_health_check to 30s ago
    worker_registry._ensure_table()
    with sqlite3.connect(worker_registry.db_path) as conn:
        conn.execute("UPDATE remote_workers SET last_health_check = ? WHERE worker_id = ?", (time.time() - 30.0, "colab-test-recovery"))
        conn.commit()

    w = worker_registry.get_worker("colab-test-recovery")
    assert w["status"] == WorkerStatus.DEGRADED.value

    # Mock health probe to succeed
    async def mock_probe(base_url):
        return True, {
            "latency_ms": 50.0,
            "gpu_name": "Tesla T4",
            "vram_total_gb": 15.0,
            "vram_free_gb": 14.5
        }, None

    monkeypatch.setattr(comfy_health_probe, "probe_endpoint", mock_probe)

    # 2. Heartbeat arrives -> should trigger probe and recover to READY
    app = FastAPI()
    app.include_router(workers_router)
    client = TestClient(app)

    try:
        resp = client.post("/api/v1/workers/heartbeat", json={
            "worker_id": "colab-test-recovery",
            "session_id": "rt-test-01"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["worker_status"] == WorkerStatus.READY.value

        # 3. Check worker in registry
        w_updated = worker_registry.get_worker("colab-test-recovery")
        assert w_updated["status"] == WorkerStatus.READY.value

        # 4. Check /api/v1/workers/status returns READY
        status_resp = client.get("/api/v1/workers/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["state"] == "ready"
        assert status_data["status"] == "ready"
        assert status_data["requires_activation"] is False
        assert status_data["gpu_name"] == "Tesla T4"
    finally:
        with sqlite3.connect(worker_registry.db_path) as conn:
            conn.execute("DELETE FROM remote_workers WHERE worker_id = 'colab-test-recovery'")
            conn.commit()


@pytest.mark.asyncio
async def test_degraded_worker_failed_probe_stays_degraded(monkeypatch):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from src.api.workers_router import workers_router
    from src.core.comfy_health_probe import comfy_health_probe
    from src.providers.worker_registry import worker_registry

    # 1. Register worker in DEGRADED
    worker_registry.register_worker(
        worker_id="colab-test-fail",
        session_id="rt-test-02",
        backend="google-colab",
        provider="comfyui",
        endpoint="https://test-tunnel-fail.trycloudflare.com",
        gpu_name="Tesla T4",
        vram_gb=15.0,
        status=WorkerStatus.DEGRADED.value
    )
    with sqlite3.connect(worker_registry.db_path) as conn:
        conn.execute("UPDATE remote_workers SET last_health_check = ? WHERE worker_id = ?", (time.time() - 30.0, "colab-test-fail"))
        conn.commit()

    # Mock health probe to FAIL
    async def mock_probe_fail(base_url):
        return False, {}, "Connection refused"

    monkeypatch.setattr(comfy_health_probe, "probe_endpoint", mock_probe_fail)

    app = FastAPI()
    app.include_router(workers_router)
    client = TestClient(app)

    try:
        # 2. Heartbeat arrives -> probe fails -> stays DEGRADED (no fake ready)
        resp = client.post("/api/v1/workers/heartbeat", json={
            "worker_id": "colab-test-fail",
            "session_id": "rt-test-02"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["worker_status"] == WorkerStatus.DEGRADED.value

        w = worker_registry.get_worker("colab-test-fail")
        assert w["status"] == WorkerStatus.DEGRADED.value
    finally:
        with sqlite3.connect(worker_registry.db_path) as conn:
            conn.execute("DELETE FROM remote_workers WHERE worker_id = 'colab-test-fail'")
            conn.commit()

