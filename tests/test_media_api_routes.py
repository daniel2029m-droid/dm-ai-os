"""
Automated Tests for Official Media REST API Endpoints & Higgsfield Provider Integration
========================================================================================
Tests:
- POST /api/media/image
- POST /api/media/video
- GET /api/media/jobs/{id}
- MediaAgent multi-provider recognition and fallback resilience
"""

import pytest
from fastapi.testclient import TestClient
from src.api.server import app
from src.agents.media_agent import MediaAgent, media_agent_instance
from src.adapters.higgsfield_adapter import higgsfield_adapter

client = TestClient(app)
API_KEY = "dm_live_secret_key_2026"
HEADERS = {"X-API-Key": API_KEY}


def test_media_agent_provider_recognition():
    """Verify MediaAgent recognizes Higgsfield provider."""
    providers = media_agent_instance.get_active_providers()
    assert "comfyui" in providers
    assert "higgsfield" in providers


@pytest.mark.asyncio
async def test_media_agent_higgsfield_image_generation():
    """Test MediaAgent generating image via Higgsfield provider."""
    res = await media_agent_instance.generate_image(
        prompt="Cyberpunk futuristic city skyline",
        provider="higgsfield",
        style="soul"
    )
    assert res["status"] == "success"
    assert res["provider"] == "higgsfield"
    assert "result" in res
    assert res["result"]["style"] == "soul"


@pytest.mark.asyncio
async def test_media_agent_higgsfield_video_generation():
    """Test MediaAgent generating video via Higgsfield provider."""
    res = await media_agent_instance.generate_video(
        image_filename="source.png",
        prompt="Slow motion rain reflection",
        provider="higgsfield",
        duration=5
    )
    assert res["status"] == "success"
    assert res["provider"] == "higgsfield"
    assert "result" in res
    assert res["result"]["duration"] == "5s"


@pytest.mark.asyncio
async def test_media_agent_fallback_to_comfyui(monkeypatch):
    """Test automatic fallback to ComfyUI if Higgsfield fails."""
    async def mock_fail_video(*args, **kwargs):
        raise RuntimeError("Simulated Higgsfield MCP outage")

    monkeypatch.setattr(higgsfield_adapter, "generate_video", mock_fail_video)

    res = await media_agent_instance.generate_video(
        image_filename="source.png",
        prompt="Fallback test prompt",
        provider="higgsfield"
    )
    assert res["status"] == "success"
    assert res["provider"] == "comfyui"
    assert "workflow_payload" in res


def test_rest_api_media_image_endpoint():
    """Test POST /api/media/image endpoint."""
    response = client.post(
        "/api/media/image",
        headers=HEADERS,
        json={
            "prompt": "Ultra-detailed portrait of a robotic architect",
            "provider": "higgsfield",
            "style": "soul",
            "aspect_ratio": "16:9"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "higgsfield"


def test_rest_api_media_video_endpoint():
    """Test POST /api/media/video endpoint."""
    response = client.post(
        "/api/media/video",
        headers=HEADERS,
        json={
            "prompt": "Cinematic camera pan across alien landscape",
            "provider": "higgsfield",
            "duration": 5,
            "mode": "cinema"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "higgsfield"


def test_rest_api_media_job_status_endpoint():
    """Test GET /api/media/jobs/{id} endpoint."""
    job_id = "higgsfield_vid_999999"
    response = client.get(f"/api/media/jobs/{job_id}", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["provider"] == "higgsfield"
