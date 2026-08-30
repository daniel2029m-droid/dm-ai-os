"""
DM AI OS — Declarative Workflow Registry & Capability Router
============================================================
Catalogs and maps creative media workflows for ComfyUI.
Enforces hardware compatibility profiles (Tesla T4 16GB VRAM constraint checking).

Tasks:
  - IMAGE_TXT2IMG: Text-to-image synthesis (FLUX.2 Klein, SD 1.5, SDXL)
  - IMAGE_IMG2IMG: Reference image variation / editing (FLUX.2 Klein, SD 1.5)
  - VIDEO_I2V: Image-to-video animation (Wan 2.1 / 2.2)
  - VIDEO_MOTION: Motion transfer / character movement (Wan 2.2 VACE)

T4 16GB Profiles:
  - T4_NATIVE: Runs entirely within 16GB VRAM without heavy CPU offloading.
  - T4_WITH_OFFLOAD: Runs using FP8/GGUF quantization and model offloading.
  - T4_EXPERIMENTAL: Large parameter models under testing.
  - T4_UNSUPPORTED: Exceeds 16GB limit, requires larger GPU (A100/H100).
"""

from enum import Enum
from typing import Dict, Any, List, Optional


class CreativeTask(str, Enum):
    IMAGE_TXT2IMG = "image_txt2img"
    IMAGE_IMG2IMG = "image_img2img"
    IMAGE_UPSCALE = "image_upscale"
    VIDEO_I2V = "video_i2v"
    VIDEO_TXT2VID = "video_txt2vid"
    VIDEO_MOTION = "video_motion"
    AUDIO_TTS = "audio_tts"
    VIDEO_LIPSYNC = "video_lipsync"


class T4Profile(str, Enum):
    T4_NATIVE = "T4_NATIVE"
    T4_WITH_OFFLOAD = "T4_WITH_OFFLOAD"
    T4_EXPERIMENTAL = "T4_EXPERIMENTAL"
    T4_UNSUPPORTED = "T4_UNSUPPORTED"


WORKFLOW_CATALOG: Dict[str, Dict[str, Any]] = {
    "zimage_turbo_txt2img": {
        "template": "zimage_turbo_txt2img",
        "task": CreativeTask.IMAGE_TXT2IMG.value,
        "model": "Z-Image Turbo",
        "checkpoint": "zimage_turbo_v1.safetensors",
        "t4_profile": T4Profile.T4_NATIVE.value,
        "min_vram_gb": 8.0,
        "recommended_vram_gb": 12.0,
        "default_width": 1024,
        "default_height": 1024,
        "steps": 8,
        "tags": ["ultra-fast", "photorealistic", "zimage", "turbo", "mvp-priority"]
    },
    "sd15_txt2img": {
        "template": "sd15_txt2img",
        "task": CreativeTask.IMAGE_TXT2IMG.value,
        "model": "Stable Diffusion 1.5",
        "checkpoint": "v1-5-pruned-emaonly-fp16.safetensors",
        "t4_profile": T4Profile.T4_NATIVE.value,
        "min_vram_gb": 4.0,
        "recommended_vram_gb": 8.0,
        "default_width": 512,
        "default_height": 768,
        "steps": 25,
        "tags": ["ultra-fast", "lightweight", "validated-e2e"]
    },
    "flux2_klein_txt2img": {
        "template": "flux2_klein_txt2img",
        "task": CreativeTask.IMAGE_TXT2IMG.value,
        "model": "FLUX.2 Klein 4B",
        "checkpoint": "flux-2-klein-4b-fp8.safetensors",
        "t4_profile": T4Profile.T4_NATIVE.value,
        "min_vram_gb": 8.0,
        "recommended_vram_gb": 12.0,
        "default_width": 768,
        "default_height": 1344,
        "steps": 20,
        "tags": ["photorealistic", "fast", "schnell", "portrait"]
    },
    "flux2_klein_img2img": {
        "template": "flux2_klein_img2img",
        "task": CreativeTask.IMAGE_IMG2IMG.value,
        "model": "FLUX.2 Klein 4B",
        "checkpoint": "flux-2-klein-4b-fp8.safetensors",
        "t4_profile": T4Profile.T4_NATIVE.value,
        "min_vram_gb": 8.0,
        "recommended_vram_gb": 12.0,
        "default_width": 768,
        "default_height": 1344,
        "steps": 20,
        "tags": ["reference-image", "variation", "editing"]
    },
    "ltx_txt2video": {
        "template": "ltx_txt2video",
        "task": CreativeTask.VIDEO_TXT2VID.value,
        "model": "LTX-Video 0.9.1 FP8",
        "checkpoint": "ltx-video-2b-v0.9.1-fp8.safetensors",
        "t4_profile": T4Profile.T4_WITH_OFFLOAD.value,
        "min_vram_gb": 12.0,
        "recommended_vram_gb": 16.0,
        "default_width": 768,
        "default_height": 512,
        "frames": 81,
        "fps": 24,
        "tags": ["fast-video", "ltx", "cinematic"]
    },
    "seedvr2_upscale": {
        "template": "seedvr2_upscale",
        "task": CreativeTask.IMAGE_UPSCALE.value,
        "model": "SeedVR2 Super Resolution",
        "checkpoint": "seedvr2_upscale_v1.safetensors",
        "t4_profile": T4Profile.T4_NATIVE.value,
        "min_vram_gb": 8.0,
        "recommended_vram_gb": 12.0,
        "scale": 4,
        "tags": ["upscale", "super-resolution", "detail-preservation"]
    },
    "qwen3_tts": {
        "template": "qwen3_tts",
        "task": CreativeTask.AUDIO_TTS.value,
        "model": "Qwen3-TTS Voice Engine",
        "checkpoint": "qwen3_tts_0.6b_fp16.safetensors",
        "t4_profile": T4Profile.T4_NATIVE.value,
        "min_vram_gb": 4.0,
        "recommended_vram_gb": 8.0,
        "tags": ["audio", "tts", "voice-synthesis"]
    },
    "float_lipsync": {
        "template": "float_lipsync",
        "task": CreativeTask.VIDEO_LIPSYNC.value,
        "model": "ComfyUI-FLOAT Lipsync",
        "checkpoint": "float_lipsync_v1.safetensors",
        "t4_profile": T4Profile.T4_WITH_OFFLOAD.value,
        "min_vram_gb": 10.0,
        "recommended_vram_gb": 14.0,
        "tags": ["lipsync", "audio-driven", "face-animation"]
    },
    "wan22_i2v": {
        "template": "wan22_i2v",
        "task": CreativeTask.VIDEO_I2V.value,
        "model": "Wan 2.1 / 2.2 I2V",
        "checkpoint": "wan2.1_i2v_720p.safetensors",
        "t4_profile": T4Profile.T4_WITH_OFFLOAD.value,
        "min_vram_gb": 14.0,
        "recommended_vram_gb": 16.0,
        "default_width": 720,
        "default_height": 1280,
        "frames": 81,
        "fps": 16,
        "tags": ["video-animation", "cinematic-motion"]
    }
}


class WorkflowRegistry:
    """
    Registry for selecting optimal workflow templates based on requested task,
    reference inputs, and GPU profile.
    """

    def __init__(self):
        self.catalog = WORKFLOW_CATALOG

    def select_workflow(
        self,
        task: CreativeTask,
        preferred_model: Optional[str] = None,
        has_reference_image: bool = False
    ) -> Dict[str, Any]:
        """
        Picks the most appropriate workflow for the given task and input conditions.
        """
        if preferred_model:
            pref = preferred_model.lower()
            if "zimage" in pref or "turbo" in pref:
                return self.catalog["zimage_turbo_txt2img"]
            if "sd15" in pref:
                return self.catalog["sd15_txt2img"]
            if "ltx" in pref:
                return self.catalog["ltx_txt2video"]
            if "seedvr" in pref or "upscale" in pref:
                return self.catalog["seedvr2_upscale"]
            if "qwen" in pref or "tts" in pref:
                return self.catalog["qwen3_tts"]
            if "float" in pref or "lipsync" in pref:
                return self.catalog["float_lipsync"]
            if "flux" in pref:
                return self.catalog["flux2_klein_img2img"] if has_reference_image else self.catalog["flux2_klein_txt2img"]

        # Task-based selection
        if task in (CreativeTask.IMAGE_UPSCALE,):
            return self.catalog["seedvr2_upscale"]
        if task in (CreativeTask.AUDIO_TTS,):
            return self.catalog["qwen3_tts"]
        if task in (CreativeTask.VIDEO_LIPSYNC,):
            return self.catalog["float_lipsync"]
        if task in (CreativeTask.VIDEO_TXT2VID,):
            return self.catalog["ltx_txt2video"]
        if task in (CreativeTask.VIDEO_I2V,):
            return self.catalog["wan22_i2v"]
        if task == CreativeTask.IMAGE_IMG2IMG or (task == CreativeTask.IMAGE_TXT2IMG and has_reference_image):
            return self.catalog["flux2_klein_img2img"]

        # Default image generation: Z-Image Turbo
        return self.catalog["zimage_turbo_txt2img"]

    def get_workflow_info(self, template_name: str) -> Optional[Dict[str, Any]]:
        clean_name = template_name.replace(".json", "")
        return self.catalog.get(clean_name)

    def list_compatible_workflows(self, available_vram_gb: float = 16.0) -> List[Dict[str, Any]]:
        """Lists all workflows executable on the given VRAM budget (e.g. Tesla T4 16GB)."""
        compatible = []
        for name, wf in self.catalog.items():
            if wf.get("min_vram_gb", 0) <= available_vram_gb:
                compatible.append({"id": name, **wf})
        return compatible


workflow_registry = WorkflowRegistry()

