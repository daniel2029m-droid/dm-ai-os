"""
Unit and Integration Tests for DM AI OS Free Model Selection System
======================================================================
Verifies:
1. Dynamic model listing via GET /api/providers/models.
2. Explicit provider and model routing.
3. Strict enforcement: NO fallback to Ollama when explicit provider fails.
4. Auto routing fallback functionality.
5. OpenRouter free model filtering.
6. API key security (no keys exposed in model/health responses).
"""

import pytest
import asyncio
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from src.providers.provider_manager import ProviderManager, BaseProviderAdapter, ProviderCapability
from src.providers.openrouter_provider import OpenRouterProviderAdapter


@pytest.fixture(autouse=True)
def mock_external_calls():
    """Autouse fixture to mock external network and CLI calls for tests."""
    with patch("src.adapters.higgsfield_adapter.HiggsfieldAdapter._get_token", return_value="mock_token"):
        yield


def test_get_all_models_endpoint():
    """Verify GET /api/providers/models returns structured provider & model list."""
    from fastapi.testclient import TestClient
    from src.api.server import app

    mock_nv_models = [{"id": "meta/llama-3.3-70b-instruct", "name": "Llama 3.3", "free": True, "local": False, "status": "available"}]
    mock_or_models = [{"id": "google/gemini-2.0-flash-exp:free", "name": "Gemini 2.0 Free", "free": True, "local": False, "status": "available"}]

    with patch("src.providers.nvidia_provider.NVIDIAImageProviderAdapter.get_models", new_callable=AsyncMock, return_value=mock_nv_models), \
         patch("src.providers.openrouter_provider.OpenRouterProviderAdapter.get_models", new_callable=AsyncMock, return_value=mock_or_models):

        c = TestClient(app)
        response = c.get("/api/providers/models")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        provider_ids = [p["provider_id"] for p in data]
        assert "auto" in provider_ids
        assert "openrouter" in provider_ids
        assert "nvidia" in provider_ids
        assert "ollama" in provider_ids


def test_api_key_security():
    """Verify API keys are NEVER exposed in models endpoint or provider listings."""
    from fastapi.testclient import TestClient
    from src.api.server import app

    c = TestClient(app)
    res_models = c.get("/api/providers/models")
    assert res_models.status_code == 200
    raw_models_json = res_models.text.lower()
    
    res_providers = c.get("/api/providers")
    assert res_providers.status_code == 200
    raw_prov_json = res_providers.text.lower()

    forbidden_snippets = ["nvapi-", "sk-or-v1-", "bearer nvapi"]
    for secret in forbidden_snippets:
        assert secret not in raw_models_json, f"Secret pattern '{secret}' leaked in /api/providers/models"
        assert secret not in raw_prov_json, f"Secret pattern '{secret}' leaked in /api/providers"


@pytest.mark.asyncio
async def test_openrouter_free_model_filtering():
    """Verify OpenRouter provider filters models to include free models."""
    adapter = OpenRouterProviderAdapter()
    
    mock_models_response = {
        "data": [
            {
                "id": "google/gemini-2.0-flash-exp:free",
                "name": "Gemini 2.0 Flash Exp Free",
                "pricing": {"prompt": "0", "completion": "0"}
            },
            {
                "id": "openai/gpt-4o",
                "name": "GPT-4o Paid",
                "pricing": {"prompt": "0.000005", "completion": "0.000015"}
            }
        ]
    }
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_models_response
        mock_get.return_value = mock_resp

        free_models = await adapter.get_models()
        assert len(free_models) == 1
        assert free_models[0]["id"] == "google/gemini-2.0-flash-exp:free"
        assert free_models[0]["free"] is True


@pytest.mark.asyncio
async def test_explicit_routing_no_fallback_on_error():
    """Verify that explicit provider selection does NOT fall back on failure."""
    pm = ProviderManager()
    
    class FailingProvider(BaseProviderAdapter):
        id = "failing_cloud"
        display_name = "Failing Cloud AI"
        capabilities = [ProviderCapability.CHAT]
        async def chat(self, messages: List[Dict[str, Any]], **kwargs):
            raise RuntimeError("Failing Cloud AI rate limit / auth error")

    pm.register(FailingProvider())
    
    with pytest.raises(RuntimeError) as exc_info:
        await pm.route_chat(
            messages=[{"role": "user", "content": "hola"}],
            preferred_provider="failing_cloud",
            model="custom-model"
        )
    assert "Failing Cloud AI rate limit / auth error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_auto_routing_fallback():
    """Verify that 'auto' mode allows fallback across providers."""
    pm = ProviderManager()
    
    class FailingProvider(BaseProviderAdapter):
        id = "failing_cloud"
        display_name = "Failing Cloud AI"
        capabilities = [ProviderCapability.CHAT]
        async def chat(self, messages: List[Dict[str, Any]], **kwargs):
            raise RuntimeError("Primary failed")

    class WorkingProvider(BaseProviderAdapter):
        id = "working_cloud"
        display_name = "Working Cloud AI"
        capabilities = [ProviderCapability.CHAT]
        async def chat(self, messages: List[Dict[str, Any]], **kwargs):
            return {"choices": [{"message": {"role": "assistant", "content": "Success"}}]}

    pm.register(FailingProvider())
    pm.register(WorkingProvider())

    with patch("src.providers.provider_manager.AUTO_CHAT_PRIORITY", ["failing_cloud", "working_cloud"]):
        res = await pm.route_chat(
            messages=[{"role": "user", "content": "hola"}],
            preferred_provider="auto"
        )
        assert res["_provider_used"] == "working_cloud"
        assert res["choices"][0]["message"]["content"] == "Success"


def test_explicit_chat_endpoint_success():
    """Test POST /api/providers/route/chat with explicit provider/model params."""
    from fastapi.testclient import TestClient
    from src.api.server import app

    c = TestClient(app)
    mock_resp = {
        "model": "qwen2.5:1.5b",
        "message": {"role": "assistant", "content": "Hola desde test"},
        "done": True,
        "_provider_used": "ollama"
    }
    with patch("src.providers.provider_manager.OllamaProviderAdapter.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = mock_resp
        payload = {
            "messages": [{"role": "user", "content": "hola"}],
            "provider": "ollama",
            "model": "qwen2.5:1.5b"
        }
        response = c.post("/api/providers/route/chat", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "_provider_used" in data
        assert data["_provider_used"] == "ollama"


@pytest.mark.asyncio
async def test_nvidia_moonshotai_kimi_model_discovery():
    """Verify NVIDIA adapter discovers moonshotai/kimi-k2.6 with owner display name & multimodal flag."""
    from src.providers.nvidia_provider import NVIDIAImageProviderAdapter

    mock_models_response = {
        "data": [
            {
                "id": "moonshotai/kimi-k2.6",
                "object": "model",
                "created": 735790403,
                "owned_by": "moonshotai"
            },
            {
                "id": "meta/llama-3.2-11b-vision-instruct",
                "object": "model",
                "created": 1787128777,
                "owned_by": "meta"
            }
        ]
    }

    adapter = NVIDIAImageProviderAdapter()
    with patch("src.config.nvidia_config.NVIDIAConfig.is_configured", new_callable=PropertyMock, return_value=True), \
         patch("httpx.AsyncClient.get") as mock_get:

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_models_response
        mock_get.return_value = mock_resp

        models = await adapter.get_models()
        assert len(models) == 2

        kimi_entry = next((m for m in models if m["id"] == "moonshotai/kimi-k2.6"), None)
        assert kimi_entry is not None
        assert kimi_entry["id"] == "moonshotai/kimi-k2.6"
        assert "MoonshotAI" in kimi_entry["name"] or "Moonshotai" in kimi_entry["name"]
        assert kimi_entry["owner"] == "moonshotai"
        assert kimi_entry["multimodal"] is True
        assert kimi_entry["free"] is True

