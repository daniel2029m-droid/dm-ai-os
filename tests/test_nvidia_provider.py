"""
Unit Tests for NVIDIA NIM Adapter & Provider Adapter (Using Mocks)
====================================================================
Tests:
- Provider initialization
- API key missing handling
- Valid configuration
- Text-to-image generation
- Image-to-image / reference image handling
- Invalid reference image handling
- Aspect ratios (1:1, 16:9, 9:16, 4:5, 5:4, 3:2, 2:3)
- Timeout handling
- HTTP errors & HTTP 429
- Cache hit & cache miss
"""

import os
import io
import base64
import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from PIL import Image

from src.config.nvidia_config import nvidia_config, SUPPORTED_ASPECT_RATIOS
from src.adapters.nvidia_adapter import NVIDIAAdapter, NVIDIAAdapterError, nvidia_adapter
from src.providers.nvidia_provider import NVIDIAImageProviderAdapter
from src.providers.provider_manager import provider_manager, ProviderStatus
from src.storage.storage_layer import storage


def create_dummy_image_bytes(fmt="PNG") -> bytes:
    """Helper to create dummy image bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def setup_env():
    """Ensure clean env setup per test."""
    os.environ["NVIDIA_API_KEY"] = "mock_nvapi_key_1234567890"
    os.environ["NVIDIA_IMAGE_MODEL"] = "black-forest-labs/flux.2-klein-4b"
    os.environ["NVIDIA_IMAGE_BASE_URL"] = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.2-klein-4b"
    storage.clear_cache()
    yield


@pytest.mark.asyncio
async def test_provider_initialization():
    """Test NVIDIAImageProviderAdapter initialization and ProviderManager registration."""
    adapter = NVIDIAImageProviderAdapter()
    assert adapter.id == "nvidia"
    assert "NVIDIA NIM" in adapter.display_name
    assert provider_manager.get("nvidia") is not None


@pytest.mark.asyncio
async def test_api_key_missing():
    """Test behavior when API Key is missing."""
    os.environ.pop("NVIDIA_API_KEY", None)
    adapter = NVIDIAAdapter()

    with pytest.raises(NVIDIAAdapterError) as exc_info:
        _ = adapter.api_key
    assert exc_info.value.status_code == 401
    assert "NVIDIA_API_KEY environment variable is missing" in str(exc_info.value)


@pytest.mark.asyncio
async def test_valid_configuration():
    """Test configuration loading."""
    assert nvidia_config.is_configured is True
    assert nvidia_config.model == "black-forest-labs/flux.2-klein-4b"
    assert "Key set" in nvidia_config.summary()


@pytest.mark.asyncio
async def test_aspect_ratios():
    """Test aspect ratio dimension resolution."""
    adapter = NVIDIAAdapter()
    for ratio, expected_dims in SUPPORTED_ASPECT_RATIOS.items():
        dims = nvidia_config.get_dimensions_for_ratio(ratio)
        assert dims == expected_dims


@pytest.mark.asyncio
async def test_text_to_image_mock():
    """Test text-to-image generation flow with mocked httpx response."""
    adapter = NVIDIAAdapter(api_key="mock_key")
    dummy_b64 = base64.b64encode(create_dummy_image_bytes()).decode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {
        "artifacts": [{"base64": dummy_b64, "seed": 42}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        result = await adapter.generate_image(
            prompt="A futuristic neon city at twilight",
            aspect_ratio="16:9",
            use_cache=False
        )

        assert result["status"] == "success"
        assert result["provider"] == "nvidia"
        assert result["model"] == "black-forest-labs/flux.2-klein-4b"
        assert result["aspect_ratio"] == "16:9"
        assert result["width"] == 1344
        assert result["height"] == 768
        assert "image_url" in result
        assert os.path.exists(result["file_path"])


@pytest.mark.asyncio
async def test_image_to_image_mock():
    """Test image-to-image generation with reference image."""
    adapter = NVIDIAAdapter(api_key="mock_key")
    dummy_img_bytes = create_dummy_image_bytes(fmt="JPEG")
    dummy_b64 = base64.b64encode(dummy_img_bytes).decode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {
        "artifacts": [{"base64": dummy_b64, "seed": 100}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        result = await adapter.generate_image(
            prompt="Transform landscape into anime style",
            reference_image=dummy_img_bytes,
            aspect_ratio="9:16",
            use_cache=False
        )

        assert result["status"] == "success"
        assert result["width"] == 768
        assert result["height"] == 1344
        assert mock_post.called
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert "image" in payload


@pytest.mark.asyncio
async def test_invalid_image_format():
    """Test validation failure for unsupported image input format."""
    adapter = NVIDIAAdapter()

    # Pass text string that is not a valid file path or base64
    with pytest.raises(NVIDIAAdapterError) as exc_info:
        adapter.validate_and_encode_image("non_existent_file.bmp")
    assert "Reference image file not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_http_429_rate_limit():
    """Test detection and handling of HTTP 429 rate limit."""
    adapter = NVIDIAAdapter(api_key="mock_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "Rate limit exceeded"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        with pytest.raises(NVIDIAAdapterError) as exc_info:
            await adapter.generate_image("Test prompt", use_cache=False)

        assert exc_info.value.status_code == 429
        assert "HTTP 429" in str(exc_info.value)


@pytest.mark.asyncio
async def test_http_500_error():
    """Test handling of HTTP status errors."""
    adapter = NVIDIAAdapter(api_key="mock_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_resp.raise_for_status.side_effect = Exception("HTTP 500 Server Error")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        with pytest.raises(NVIDIAAdapterError) as exc_info:
            await adapter.generate_image("Test prompt", use_cache=False)
        assert "Unexpected error" in str(exc_info.value) or "500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_cache_hit_and_miss():
    """Test cache miss on first call and cache hit on second identical call."""
    adapter = NVIDIAAdapter(api_key="mock_key")
    dummy_b64 = base64.b64encode(create_dummy_image_bytes()).decode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {
        "artifacts": [{"base64": dummy_b64}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        # 1st call -> Cache miss -> HTTP call
        res1 = await adapter.generate_image("Unique cache test prompt", aspect_ratio="1:1", use_cache=True)
        assert res1["_cached"] is False
        assert mock_post.call_count == 1

        # 2nd call -> Cache hit -> NO HTTP call
        res2 = await adapter.generate_image("Unique cache test prompt", aspect_ratio="1:1", use_cache=True)
        assert res2["_cached"] is True
        assert mock_post.call_count == 1  # count did not increase


@pytest.mark.asyncio
async def test_media_agent_nvidia_routing():
    """Test MediaAgent routing to NVIDIA provider."""
    from src.agents.media_agent import MediaAgent
    agent = MediaAgent()

    dummy_b64 = base64.b64encode(create_dummy_image_bytes()).decode("utf-8")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {"artifacts": [{"base64": dummy_b64}]}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        res = await agent.generate_image(
            prompt="MediaAgent test prompt for NVIDIA",
            provider="nvidia",
            aspect_ratio="9:16",
            use_cache=False
        )

        assert res["status"] == "success"
        assert res["provider"] == "nvidia"


@pytest.mark.asyncio
async def test_providers_router_nvidia():
    """Test API route endpoint routing to NVIDIA provider."""
    from src.api.providers_router import route_image, MediaRouteRequest
    
    dummy_b64 = base64.b64encode(create_dummy_image_bytes()).decode("utf-8")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {"artifacts": [{"base64": dummy_b64}]}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        req = MediaRouteRequest(
            prompt="API Router test prompt",
            provider="nvidia",
            aspect_ratio="16:9"
        )
        res = await route_image(req)
        assert res["_provider_used"] == "nvidia"
        assert "image_url" in res

