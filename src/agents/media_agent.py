"""
MediaAgent - Image & Video Generation with RunPod & ComfyUI Cloud Integration (Phase 2 Priority #6).
Reuses ComfyUI API payload builder & Grok video workflow from agent_bot/comfy_api.py.
Enforces GPUManager $10 budget guardrail.
"""

import asyncio
import logging
from typing import Dict, Any, List

from ..core.plugin_manager import BasePlugin, plugin_manager
from ..core.gpu_manager import gpu_mgr

log = logging.getLogger("media_agent")

def build_grok_video_payload(image_filename: str, prompt: str) -> Dict[str, Any]:
    """Reused payload builder from agent_bot/comfy_api.py."""
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
        return "GPU-accelerated image and video generation agent utilizing RunPod and ComfyUI Cloud API."

    async def initialize(self) -> bool:
        log.info("[MediaAgent] Initialized.")
        return True

    async def generate_image(self, prompt: str, resolution: str = "1024x1024") -> Dict[str, Any]:
        gpu_target, reason = gpu_mgr.evaluate_workload("image_generation", {"prompt": prompt})
        log.info(f"[MediaAgent] Image Gen Target: {gpu_target} ({reason})")

        payload = {
            "prompt": prompt,
            "resolution": resolution,
            "target": gpu_target,
            "engine": "ComfyUI / SDXL"
        }

        return {
            "status": "success",
            "gpu_target": gpu_target,
            "reason": reason,
            "workflow_payload": payload
        }

    async def generate_video(self, image_filename: str, prompt: str) -> Dict[str, Any]:
        gpu_target, reason = gpu_mgr.evaluate_workload("video_generation", {"prompt": prompt})
        log.info(f"[MediaAgent] Video Gen Target: {gpu_target} ({reason})")

        payload = build_grok_video_payload(image_filename, prompt)

        return {
            "status": "success",
            "gpu_target": gpu_target,
            "reason": reason,
            "workflow_payload": payload
        }

    async def execute_action(self, action_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action_name == "generate_image":
            prompt = payload.get("prompt", "A high quality image")
            res = payload.get("resolution", "1024x1024")
            return await self.generate_image(prompt, res)

        if action_name == "generate_video":
            img = payload.get("image_filename", "image.png")
            p = payload.get("prompt", "Video motion")
            return await self.generate_video(img, p)

        return {"status": "error", "message": f"Unknown action '{action_name}'."}

# Register instance
media_agent_instance = MediaAgent()
plugin_manager.register_plugin(media_agent_instance)
