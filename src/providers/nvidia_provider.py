"""
DM AI OS — NVIDIA Image Provider Adapter
=========================================
Concrete provider adapter integrating NVIDIA NIM FLUX.2 Klein 4B.
Inherits from BaseProviderAdapter to plug directly into ProviderManager router.

Prepares structure for multi-provider setup:
  ProviderManager
    ├── HiggsfieldProviderAdapter
    ├── NVIDIAImageProviderAdapter
    └── RunPodImageProvider (prepared for future integration)
"""

import time
import logging
from typing import Dict, Any, List, Tuple

from .provider_manager import BaseProviderAdapter, ProviderStatus, ProviderCapability
from ..config.nvidia_config import nvidia_config
from ..adapters.nvidia_adapter import nvidia_adapter, NVIDIAAdapterError

log = logging.getLogger("nvidia_provider")


class NVIDIAImageProviderAdapter(BaseProviderAdapter):
    """
    NVIDIA NIM FLUX.2 Klein 4B Image Provider Adapter.
    Integrates smoothly with DM AI OS ProviderManager.
    """
    id = "nvidia"
    display_name = "NVIDIA NIM API"
    capabilities = [ProviderCapability.IMAGE, ProviderCapability.CHAT, ProviderCapability.CODE]
    is_local = False

    def __init__(self):
        self._adapter = nvidia_adapter
        self.nim_api_url = "https://integrate.api.nvidia.com/v1"

    def get_account_info(self) -> str:
        if nvidia_config.is_configured:
            return "NVIDIA NIM (Configured)"
        return "NVIDIA_API_KEY not configured"

    async def health_check(self) -> Tuple[ProviderStatus, float, str]:
        """Check provider health and latency."""
        t0 = time.monotonic()
        if not nvidia_config.is_configured:
            return (ProviderStatus.AUTH_EXPIRED, 0.0, self.get_account_info())

        try:
            import httpx
            headers = {"Authorization": f"Bearer {nvidia_config.api_key}"}
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.nim_api_url}/models", headers=headers)
                latency = round((time.monotonic() - t0) * 1000, 1)
                
                if r.status_code in (200, 405, 422):
                    return (ProviderStatus.AVAILABLE, latency, self.get_account_info())
                elif r.status_code in (401, 403):
                    return (ProviderStatus.AUTH_EXPIRED, latency, self.get_account_info())
                elif r.status_code == 429:
                    return (ProviderStatus.NO_CREDITS, latency, self.get_account_info())
                else:
                    return (ProviderStatus.AVAILABLE, latency, self.get_account_info())
        except Exception as e:
            latency = round((time.monotonic() - t0) * 1000, 1)
            log.warning(f"[NVIDIAProvider] Health check ping exception: {e}")
            return (ProviderStatus.AVAILABLE, latency, self.get_account_info())

    async def get_models(self) -> List[Dict[str, Any]]:
        """Fetch available NIM models from NVIDIA API with owner namespaces & multimodal metadata."""
        if not nvidia_config.is_configured:
            return []
        try:
            import httpx
            headers = {"Authorization": f"Bearer {nvidia_config.api_key}"}
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(f"{self.nim_api_url}/models", headers=headers)
            if r.status_code != 200:
                return []
            data = r.json().get("data", [])
            models = []
            
            multimodal_keywords = [
                "vision", "vlm", "multimodal", "kimi", "fuyu", "deplot", "kosmos",
                "neva", "vila", "clip", "vl", "omni", "image", "video", "parse"
            ]

            for m in data:
                m_id = m.get("id", "")
                owner_raw = m.get("owned_by", "")
                if m_id:
                    if "/" in m_id:
                        owner_part, model_part = m_id.split("/", 1)
                        owner_display = owner_part.replace("-", " ").title().replace("Ai", "AI")
                        model_display = model_part.replace("-", " ").title()
                        name = f"{owner_display} / {model_display}"
                    else:
                        name = m_id.replace("-", " ").title()

                    is_multimodal = any(k in m_id.lower() for k in multimodal_keywords)

                    models.append({
                        "id": m_id,
                        "name": name,
                        "owner": owner_raw or (m_id.split("/")[0] if "/" in m_id else "nvidia"),
                        "free": True,  # Available with API Key build credits
                        "multimodal": is_multimodal,
                        "local": False,
                        "status": "available"
                    })
            return models
        except Exception as e:
            log.warning(f"[NVIDIAProvider] Error fetching models: {e}")
            return []

    async def chat(self, messages: List[Dict], model: str = "meta/llama-3.3-70b-instruct", **kwargs) -> Dict[str, Any]:
        """Execute chat completions via NVIDIA NIM API."""
        if not nvidia_config.is_configured:
            raise RuntimeError("NVIDIA_API_KEY environment variable is missing. Set NVIDIA_API_KEY in .env before using NVIDIA NIM.")

        import httpx
        headers = {
            "Authorization": f"Bearer {nvidia_config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2048)
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{self.nim_api_url}/chat/completions", json=payload, headers=headers)

        if r.status_code == 429:
            raise RuntimeError(f"NVIDIA NIM Rate Limit Exceeded (HTTP 429) for model '{model}'. Select another model or wait.")
        elif r.status_code in (401, 403):
            raise RuntimeError(f"NVIDIA NIM Authentication Error (HTTP {r.status_code}). Check NVIDIA_API_KEY in .env.")
        elif r.status_code != 200:
            err_msg = r.text
            try:
                err_msg = r.json().get("error", {}).get("message", err_msg)
            except Exception:
                pass
            raise RuntimeError(f"NVIDIA NIM API Error ({r.status_code}): {err_msg}")

        return r.json()

    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Generate image using FLUX.2 Klein 4B via NVIDIA NIM adapter.
        """
        aspect_ratio = kwargs.get("aspect_ratio", "1:1")
        reference_image = kwargs.get("reference_image") or kwargs.get("image_url") or kwargs.get("image")
        seed = kwargs.get("seed")
        steps = kwargs.get("steps") or kwargs.get("num_inference_steps")
        timeout = kwargs.get("timeout")
        metadata = kwargs.get("metadata")
        use_cache = kwargs.get("use_cache", True)

        res = await self._adapter.generate_image(
            prompt=prompt,
            reference_image=reference_image,
            aspect_ratio=aspect_ratio,
            seed=seed,
            steps=steps,
            timeout=timeout,
            metadata=metadata,
            use_cache=use_cache
        )

        url = res.get("image_url", "")
        res["choices"] = [{
            "message": {
                "role": "assistant",
                "content": f"🖼️ **Imagen generada por NVIDIA NIM (FLUX.2 Klein 4B):**\n\n![Imagen]({url})\n\n[📥 Descargar Imagen]({url})"
            }
        }]
        res["_provider_used"] = "nvidia"
        return res




