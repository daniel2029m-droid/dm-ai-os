"""
DM AI OS — OpenRouter Free Models Provider Adapter
===================================================
Concrete provider adapter integrating OpenRouter's official API.
Filters models to only include 100% FREE models (prompt=0, completion=0).
Inherits from BaseProviderAdapter to plug directly into ProviderManager router.
"""

import os
import time
import logging
import httpx
from typing import Dict, Any, List, Tuple

from .provider_manager import BaseProviderAdapter, ProviderStatus, ProviderCapability

log = logging.getLogger("openrouter_provider")


class OpenRouterProviderAdapter(BaseProviderAdapter):
    """
    OpenRouter API Provider Adapter.
    Provides access to free models hosted on OpenRouter.
    """
    id = "openrouter"
    display_name = "OpenRouter (Free Models)"
    capabilities = [
        ProviderCapability.CHAT,
        ProviderCapability.CODE,
    ]
    is_local = False

    def __init__(self):
        self.base_url = "https://openrouter.ai/api/v1"

    @property
    def api_key(self) -> str:
        return os.getenv("OPENROUTER_API_KEY", "").strip()

    def get_account_info(self) -> str:
        key = self.api_key
        if key:
            snippet = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"
            return f"OpenRouter (Key: {snippet})"
        return "OpenRouter (Free Access)"

    async def health_check(self) -> Tuple[ProviderStatus, float, str]:
        """Check provider health and latency."""
        t0 = time.monotonic()
        headers = {"User-Agent": "DM-AI-OS/1.5"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/models", headers=headers)
                latency = round((time.monotonic() - t0) * 1000, 1)
                if r.status_code == 200:
                    return (ProviderStatus.AVAILABLE, latency, self.get_account_info())
                elif r.status_code in (401, 403):
                    return (ProviderStatus.AUTH_EXPIRED, latency, self.get_account_info())
                elif r.status_code == 429:
                    return (ProviderStatus.NO_CREDITS, latency, self.get_account_info())
                else:
                    return (ProviderStatus.UNAVAILABLE, latency, f"HTTP {r.status_code}")
        except Exception as e:
            latency = round((time.monotonic() - t0) * 1000, 1)
            log.warning(f"[OpenRouterProvider] Health check failed: {e}")
            return (ProviderStatus.UNAVAILABLE, latency, str(e))

    async def get_models(self) -> List[Dict[str, Any]]:
        """
        Fetch available models from OpenRouter API.
        Returns ONLY truly free models (pricing prompt == 0 and completion == 0).
        """
        headers = {"User-Agent": "DM-AI-OS/1.5"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(f"{self.base_url}/models", headers=headers)
            if r.status_code != 200:
                return []
            
            data = r.json().get("data", [])
            free_models = []
            for m in data:
                model_id = m.get("id", "")
                pricing = m.get("pricing", {})
                prompt_cost = float(pricing.get("prompt", "0") or 0)
                completion_cost = float(pricing.get("completion", "0") or 0)
                
                # Check if free by pricing or :free suffix
                is_free = (prompt_cost == 0 and completion_cost == 0) or model_id.endswith(":free")
                if is_free and model_id:
                    free_models.append({
                        "id": model_id,
                        "name": m.get("name") or model_id,
                        "free": True,
                        "local": False,
                        "status": "available",
                        "context_length": m.get("context_length", 4096)
                    })
            return free_models
        except Exception as e:
            log.warning(f"[OpenRouterProvider] Error fetching models: {e}")
            return []

    async def chat(self, messages: List[Dict], model: str = "google/gemini-2.0-flash-exp:free", **kwargs) -> Dict[str, Any]:
        """
        Execute chat completions using OpenRouter API.
        """
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://dmai-os.local",
            "X-Title": "DM AI OS",
            "User-Agent": "DM-AI-OS/1.5"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": model,
            "messages": messages
        }
        if "temperature" in kwargs:
            payload["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            payload["max_tokens"] = kwargs["max_tokens"]

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)

        if r.status_code == 429:
            raise RuntimeError(f"OpenRouter Rate Limit Exceeded (HTTP 429) for model '{model}'. Select another free model.")
        elif r.status_code in (401, 403):
            raise RuntimeError(f"OpenRouter Authentication Error (HTTP {r.status_code}) for model '{model}'.")
        elif r.status_code != 200:
            err_msg = r.text
            try:
                err_json = r.json()
                err_msg = err_json.get("error", {}).get("message", err_msg)
            except Exception:
                pass
            raise RuntimeError(f"OpenRouter API Error ({r.status_code}): {err_msg}")

        return r.json()
