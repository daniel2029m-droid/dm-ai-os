"""
Unit Tests for RunPod Providers & ProviderManager Integration
================================================================
Tests:
- RunPodImageProviderAdapter registration & capabilities
- RunPodVideoProviderAdapter registration & video pipeline
- Image-to-Video and Motion Transfer routing
- ProviderManager AUTO fallback order containing RunPod
"""

import os
import pytest
from unittest.mock import patch, AsyncMock

from src.providers.provider_manager import provider_manager, ProviderCapability
from src.providers.runpod_provider import RunPodImageProviderAdapter
from src.providers.runpod_video_provider import RunPodVideoProviderAdapter
from src.storage.storage_layer import storage


@pytest.fixture(autouse=True)
def setup_env():
    os.environ["RUNPOD_API_KEY"] = "mock_runpod_key_12345"
    storage.clear_cache()
    yield


@pytest.mark.asyncio
async def test_runpod_provider_registration():
    """Test RunPod provider registration in ProviderManager."""
    provider_manager.register(RunPodImageProviderAdapter())
    provider_manager.register(RunPodVideoProviderAdapter())

    img_adapter = provider_manager.get("runpod")
    vid_adapter = provider_manager.get("runpod_video")

    assert img_adapter is not None
    assert vid_adapter is not None
    assert img_adapter.id == "runpod"
    assert vid_adapter.id == "runpod_video"
    assert ProviderCapability.IMAGE in img_adapter.capabilities
    assert ProviderCapability.VIDEO in vid_adapter.capabilities



@pytest.mark.asyncio
async def test_runpod_image_generation_routing():
    """Test routing image generation through RunPodImageProviderAdapter."""
    adapter = RunPodImageProviderAdapter()

    mock_res = {
        "status": "success",
        "provider": "runpod",
        "model": "black-forest-labs/FLUX.2-klein-4B",
        "image_url": "/api/providers/uploads/runpod_out.png",
        "file_path": "/tmp/runpod_out.png",
        "latency_ms": 1500.0,
        "_cached": False
    }

    with patch.object(adapter._adapter, "generate_image", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_res
        res = await adapter.generate_image("Neon cyberpunk portrait", aspect_ratio="9:16")

        assert res["status"] == "success"
        assert res["provider"] == "runpod"
        assert "choices" in res


@pytest.mark.asyncio
async def test_runpod_video_motion_transfer_routing():
    """Test Video Provider Motion Transfer routing (Reference Image + Reference Video)."""
    vid_adapter = RunPodVideoProviderAdapter()

    mock_res = {
        "status": "success",
        "provider": "runpod_video",
        "model": "wan2.2-i2v",
        "mode": "motion_transfer",
        "video_url": "/api/providers/uploads/wan22_motion.mp4",
        "file_path": "/tmp/wan22_motion.mp4",
        "latency_ms": 3200.0,
        "choices": [],
        "_cached": False
    }

    with patch.object(vid_adapter._adapter, "gpu_session") as mock_sess, \
         patch.object(vid_adapter._adapter, "upload_file", new_callable=AsyncMock) as mock_upload, \
         patch.object(vid_adapter._adapter, "submit_job", new_callable=AsyncMock) as mock_submit, \
         patch.object(vid_adapter._adapter, "get_job_result", new_callable=AsyncMock) as mock_result, \
         patch.object(vid_adapter._adapter, "download_result", new_callable=AsyncMock) as mock_dl:

        mock_sess.return_value.__aenter__.return_value = vid_adapter._adapter
        mock_upload.return_value = "input_uploaded.png"
        mock_submit.return_value = {"job_id": "job_vid_123"}
        mock_result.return_value = {"completed": True}
        mock_dl.return_value = {
            "image_url": "/api/providers/uploads/wan22_motion.mp4",
            "file_path": "/tmp/wan22_motion.mp4"
        }

        res = await vid_adapter.generate_video(
            prompt="Animate character performing dance moves",
            reference_image="character.png",
            reference_video="dance_motion.mp4",
            use_cache=False
        )

        assert res["status"] == "success"
        assert res["provider"] == "runpod_video"
        assert res["mode"] == "motion_transfer"
        assert "video_url" in res
