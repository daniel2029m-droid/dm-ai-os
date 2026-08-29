"""
MediaAgent - Image & Video Generation with ProviderManager & Higgsfield MCP.
======================================================================================
Multi-provider media agent:
- All media routing is delegated through ProviderManager (AI Router)
- Supports Higgsfield MCP Connector (https://mcp.higgsfield.ai/mcp) as primary provider
- Secondary Provider & Fallback: ComfyUI / RunPod Cloud API & Grok Video Node
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional

from ..core.plugin_manager import BasePlugin, plugin_manager
from ..core.gpu_manager import gpu_mgr
from ..providers.provider_manager import provider_manager
from ..adapters.higgsfield_adapter import higgsfield_adapter
from ..core.creative_engine import creative_engine

log = logging.getLogger("media_agent")


def build_grok_video_payload(image_filename: str, prompt: str) -> Dict[str, Any]:
    return {
        "3": {"class_type": "LoadImage", "inputs": {"image": image_filename, "upload": "image"}},
        "1": {"class_type": "GrokVideoNode", "inputs": {"image": ["3", 0], "model": "grok-imagine-video-beta", "prompt": prompt, "resolution": "720p", "seed": 880926991, "control_after_generate": "randomize"}},
        "2": {"class_type": "SaveVideo", "inputs": {"video": ["1", 0], "filename_prefix": "video/Grok", "format": "auto", "codec": "auto"}}
    }


class MediaAgent(BasePlugin):
    @property
    def plugin_name(self) -> str:
        return "media"

    @property
    def description(self) -> str:
        return "Multi-provider image and video generation agent utilizing ProviderManager and Higgsfield MCP."

    async def initialize(self) -> bool:
        log.info(f"[MediaAgent] Initialized with ProviderManager. Active providers: {[p['id'] for p in provider_manager.list_providers()]}")
        return True

    def get_active_providers(self) -> List[str]:
        return [p["id"] for p in provider_manager.list_providers()]

    async def generate_image(
        self,
        prompt: str,
        resolution: str = "1024x1024",
        provider: str = "auto",
        **kwargs
    ) -> Dict[str, Any]:
        """Generate image via ProviderManager AI Router with auto-fallback."""
        target_provider = provider.lower()
        log.info(f"[MediaAgent] Request generate_image via ProviderManager (Provider: {target_provider}, Prompt: '{prompt[:30]}...')")

        if target_provider in ("creative", "comfy"):
            template = kwargs.get("template", "flux2_klein_txt2img")
            return await creative_engine.run_workflow(template_name_or_path=template, prompt=prompt, parameters=kwargs)

        try:
            res = await provider_manager.route_image(
                prompt=prompt,
                preferred_provider=target_provider,
                aspect_ratio=kwargs.get("aspect_ratio", "1:1"),
                count=kwargs.get("count", 1)
            )
            return {
                "status": "success",
                "provider": res.get("_provider_used", target_provider),
                "engine": "ProviderManager AI Router",
                "gpu_target": "higgsfield_mcp_cloud",
                "workflow_payload": res,
                "result": res
            }
        except Exception as e:
            log.warning(f"[MediaAgent] ProviderManager image generation failed, falling back to ComfyUI: {e}")

        # Fallback / Default ComfyUI execution
        gpu_target, reason = gpu_mgr.evaluate_workload("image_generation", {"prompt": prompt})
        payload = {
            "prompt": prompt,
            "resolution": resolution,
            "target": gpu_target,
            "engine": "ComfyUI / SDXL"
        }
        return {
            "status": "success",
            "provider": "comfyui",
            "gpu_target": gpu_target,
            "reason": reason,
            "workflow_payload": payload
        }

    async def generate_video(
        self,
        image_filename: str,
        prompt: str,
        provider: str = "auto",
        **kwargs
    ) -> Dict[str, Any]:
        """Generate video via ProviderManager AI Router with auto-fallback."""
        target_provider = provider.lower()
        log.info(f"[MediaAgent] Request generate_video via ProviderManager (Provider: {target_provider}, Prompt: '{prompt[:30]}...')")

        if target_provider in ("creative", "comfy"):
            template = kwargs.get("template", "wan22_i2v")
            params = dict(kwargs)
            params["image_filename"] = image_filename
            return await creative_engine.run_workflow(template_name_or_path=template, prompt=prompt, parameters=params)

        try:
            res = await provider_manager.route_video(
                prompt=prompt,
                preferred_provider=target_provider,
                image_url=image_filename if image_filename != "image.png" else None,
                duration=kwargs.get("duration", 5),
                aspect_ratio=kwargs.get("aspect_ratio", "16:9")
            )
            return {
                "status": "success",
                "provider": res.get("_provider_used", target_provider),
                "engine": "ProviderManager AI Router",
                "gpu_target": "higgsfield_mcp_cloud",
                "workflow_payload": res,
                "result": res
            }
        except Exception as e:
            log.warning(f"[MediaAgent] ProviderManager video generation failed, falling back to ComfyUI: {e}")

        # Fallback / Default ComfyUI execution
        gpu_target, reason = gpu_mgr.evaluate_workload("video_generation", {"prompt": prompt})
        payload = build_grok_video_payload(image_filename, prompt)
        return {
            "status": "success",
            "provider": "comfyui",
            "gpu_target": gpu_target,
            "reason": reason,
            "workflow_payload": payload
        }

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        return await higgsfield_adapter.get_job_status(job_id)

    async def download_job_result(self, job_id: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        return await higgsfield_adapter.download_result(job_id, output_path=output_path)

    async def execute_action(self, action_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        p = dict(payload)
        provider = p.pop("provider", "auto")

        if action_name == "generate_image":
            prompt = p.pop("prompt", "A high quality image")
            res = p.pop("resolution", "1024x1024")
            return await self.generate_image(prompt, res, provider=provider, **p)

        if action_name == "generate_video":
            img = p.pop("image_filename", p.pop("image_url", "image.png"))
            prompt_text = p.pop("prompt", "Video motion")
            return await self.generate_video(img, prompt_text, provider=provider, **p)

        if action_name == "get_job_status":
            job_id = p.pop("job_id", p.pop("id", None))
            return await self.get_job_status(job_id)

        if action_name == "download_result":
            job_id = p.pop("job_id", p.pop("id", None))
            path = p.pop("output_path", None)
            return await self.download_job_result(job_id, output_path=path)

        return {"status": "error", "message": f"Unknown action '{action_name}'."}


# Register instance
media_agent_instance = MediaAgent()
plugin_manager.register_plugin(media_agent_instance)
