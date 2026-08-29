"""
DM AI OS — RunPod Image & Video Provider Adapter
=================================================
Concrete provider adapter integrating self-hosted FLUX.2 Klein 4B & Video AI on RunPod GPU.
Inherits from BaseProviderAdapter to plug directly into ProviderManager router.

Capabilities supported:
- Text-to-Image
- Image-to-Image / Reference Image / Image Editing
- Image-to-Video
- Video-to-Video
- Motion Transfer (Reference Image + Reference Video)
"""

import time
import logging
from typing import Dict, Any, List, Tuple

from .provider_manager import BaseProviderAdapter, ProviderStatus, ProviderCapability

from ..config.runpod_config import runpod_config

log = logging.getLogger("runpod_provider")

class RunPodImageProviderAdapter(BaseProviderAdapter):

    """
    RunPod GPU Image & Video Provider Adapter.
    Self-hosted FLUX.2 Klein 4B & Video AI Pipeline on RunPod Cloud Infrastructure.
    """
    id = "runpod"
    display_name = "RunPod GPU (FLUX.2 & Video AI)"
    capabilities = [
        ProviderCapability.IMAGE,
        ProviderCapability.VIDEO,
        ProviderCapability.LOCAL,
    ]
    is_local = False

    # Capability feature flags
    supports_text_to_image = True
    supports_image_to_image = True
    supports_reference_image = True
    supports_image_editing = True
    supports_image_to_video = True
    supports_video_to_video = True
    supports_reference_video = True
    supports_motion_transfer = True

    def __init__(self):
        from ..adapters.runpod_adapter import runpod_adapter
        self._adapter = runpod_adapter


    def get_account_info(self) -> str:
        if runpod_config.is_configured:
            pod_str = f"Pod: {runpod_config.pod_id}" if runpod_config.pod_id else "Serverless / Dynamic Pods"
            return f"RunPod GPU ({pod_str})"
        return "RUNPOD_API_KEY not configured"

    async def health_check(self) -> Tuple[ProviderStatus, float, str]:
        """Check RunPod provider health and latency."""
        status_str, latency, info = await self._adapter.health_check()
        if status_str == "available":
            return (ProviderStatus.AVAILABLE, latency, self.get_account_info())
        elif status_str == "auth_expired":
            return (ProviderStatus.AUTH_EXPIRED, latency, self.get_account_info())
        else:
            # If key configured but pod stopped, report available for auto-start
            if runpod_config.is_configured:
                return (ProviderStatus.AVAILABLE, latency, f"RunPod AutoStart Ready ({self.get_account_info()})")
            return (ProviderStatus.UNAVAILABLE, latency, info)

    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate image using FLUX.2 Klein 4B on RunPod GPU."""
        aspect_ratio = kwargs.get("aspect_ratio", "1:1")
        reference_image = kwargs.get("reference_image") or kwargs.get("image_url") or kwargs.get("image")
        seed = kwargs.get("seed")
        steps = kwargs.get("steps")
        use_cache = kwargs.get("use_cache", True)

        res = await self._adapter.generate_image(
            prompt=prompt,
            reference_image=reference_image,
            aspect_ratio=aspect_ratio,
            seed=seed,
            steps=steps,
            use_cache=use_cache
        )

        url = res.get("image_url", "")
        res["choices"] = [{
            "message": {
                "role": "assistant",
                "content": f"🖼️ **Imagen generada por RunPod GPU (FLUX.2 Klein 4B):**\n\n![Imagen]({url})\n\n[📥 Descargar Imagen]({url})"
            }
        }]
        res["_provider_used"] = "runpod"
        return res

    async def generate_video(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate video on RunPod GPU (delegates to Video Provider pipeline)."""
        from .runpod_video_provider import RunPodVideoProviderAdapter
        video_adapter = RunPodVideoProviderAdapter()
        return await video_adapter.generate_video(prompt=prompt, **kwargs)




