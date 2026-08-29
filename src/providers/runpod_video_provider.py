"""
DM AI OS — RunPod Video Provider & Motion Transfer Pipeline
============================================================
Handles Video AI generation tasks on RunPod GPU infrastructure:
- Image-to-Video (Wan 2.2 I2V)
- Video-to-Video (V2V transformation)
- Motion Transfer (Reference Character Image + Reference Motion Video via Wan 2.2 + VACE)
"""

import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, Tuple


from .provider_manager import BaseProviderAdapter, ProviderStatus, ProviderCapability

from ..config.runpod_config import runpod_config
from ..storage.storage_layer import storage
from ..providers.provider_history import provider_history

log = logging.getLogger("runpod_video_provider")


class RunPodVideoProviderAdapter(BaseProviderAdapter):

    """
    RunPod GPU Video AI Adapter.
    Executes Wan 2.2 I2V, VACE Motion Transfer, and V2V workflows.
    """
    id = "runpod_video"
    display_name = "RunPod Video AI (Wan 2.2 & Motion Transfer)"
    capabilities = [
        ProviderCapability.VIDEO,
        ProviderCapability.LOCAL,
    ]
    is_local = False

    def __init__(self):
        from ..adapters.runpod_adapter import runpod_adapter
        self._adapter = runpod_adapter


    def get_account_info(self) -> str:
        return f"RunPod Video Pipeline ({runpod_config.video_model})"

    async def health_check(self) -> Tuple[ProviderStatus, float, str]:
        st, latency, info = await self._adapter.health_check()
        return (ProviderStatus.AVAILABLE if st == "available" else ProviderStatus.UNAVAILABLE, latency, info)

    async def generate_video(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Main video generation router.
        Supports:
        - Image-to-Video: kwargs contains image_url / reference_image
        - Motion Transfer: kwargs contains reference_image AND reference_video
        """
        ref_image = kwargs.get("reference_image") or kwargs.get("image_url") or kwargs.get("image")
        ref_video = kwargs.get("reference_video") or kwargs.get("video_url") or kwargs.get("video")
        duration = kwargs.get("duration", 5)
        fps = kwargs.get("fps", 16)
        seed = kwargs.get("seed", 42)
        use_cache = kwargs.get("use_cache", True)

        # Detect workflow mode
        mode = "text_to_video"
        if ref_image and ref_video:
            mode = "motion_transfer"
        elif ref_image:
            mode = "image_to_video"
        elif ref_video:
            mode = "video_to_video"

        cache_key_data = {
            "provider": "runpod_video",
            "model": runpod_config.video_model,
            "mode": mode,
            "prompt": prompt.strip(),
            "duration": duration,
            "seed": seed,
            "ref_image": str(ref_image) if ref_image else None,
            "ref_video": str(ref_video) if ref_video else None,
        }

        if use_cache:
            cached = storage.get_cache("runpod_video", cache_key_data)
            if cached:
                log.info(f"[RunPodVideoProvider] CACHE HIT for video prompt: '{prompt[:40]}...'")
                cached["_cached"] = True
                return cached

        t0 = time.monotonic()
        log.info(f"[RunPodVideoProvider] Executing {mode} (Model: {runpod_config.video_model})")

        async with self._adapter.gpu_session():
            wf_file_map = {
                "motion_transfer": "wan22_motion_transfer.json",
                "image_to_video": "wan22_i2v.json",
                "video_to_video": "wan22_motion_transfer.json",
                "text_to_video": "wan22_i2v.json",
            }
            wf_file = Path(__file__).parent.parent.parent / "workflows" / "runpod" / wf_file_map[mode]
            wf_template = json.loads(wf_file.read_text(encoding="utf-8")) if wf_file.exists() else {}

            # Upload inputs to pod
            image_fn = await self._adapter.upload_file(ref_image) if ref_image else None
            video_fn = await self._adapter.upload_file(ref_video) if ref_video else None

            # Populate template placeholders
            if mode == "motion_transfer":
                if "2" in wf_template and image_fn:
                    wf_template["2"]["inputs"]["image"] = image_fn
                if "3" in wf_template and video_fn:
                    wf_template["3"]["inputs"]["video"] = video_fn
                if "5" in wf_template:
                    wf_template["5"]["inputs"]["text"] = prompt
            else:
                if "2" in wf_template and image_fn:
                    wf_template["2"]["inputs"]["image"] = image_fn
                if "3" in wf_template:
                    wf_template["3"]["inputs"]["text"] = prompt

            # Submit & await job
            job = await self._adapter.submit_job(wf_template)
            job_id = job["job_id"]
            _ = await self._adapter.get_job_result(job_id)

            # Download video result
            out = await self._adapter.download_result(f"wan22_output_{job_id[:8]}.mp4")

        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        video_url = out["image_url"]  # Served via uploads router

        result = {
            "status": "success",
            "provider": "runpod_video",
            "model": runpod_config.video_model,
            "mode": mode,
            "prompt": prompt,
            "video_url": video_url,
            "file_path": out["file_path"],
            "latency_ms": latency_ms,
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": f"🎬 **Video generado por RunPod Video AI ({mode}):**\n\n![Video]({video_url})\n\n[📥 Descargar MP4]({video_url})"
                }
            }],
            "_cached": False
        }

        storage.set_cache("runpod_video", cache_key_data, result)
        provider_history.record(
            provider="runpod_video", capability="video", prompt=prompt, model=runpod_config.video_model,
            result_url=video_url, duration_ms=latency_ms, status="ok"
        )
        return result



