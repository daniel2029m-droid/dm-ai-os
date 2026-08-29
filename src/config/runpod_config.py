"""
RunPod GPU Infrastructure — Configuration for DM AI OS
=========================================================
Reads all configuration values from environment variables.
NEVER hardcode API keys or credentials in this file.

Variables:
  RUNPOD_API_KEY               — RunPod User API Key
  RUNPOD_ENDPOINT_ID           — Serverless Endpoint ID (optional)
  RUNPOD_POD_ID                — Dedicated Pod ID (optional)
  RUNPOD_TEMPLATE_ID           — Pod Template ID
  RUNPOD_VOLUME_ID             — Pod Volume ID
  RUNPOD_NETWORK_VOLUME_ID     — Network Volume ID
  RUNPOD_AUTO_START            — Auto-start GPU on request (default: true)
  RUNPOD_AUTO_STOP             — Auto-stop GPU when idle (default: true)
  RUNPOD_IDLE_TIMEOUT_SECONDS  — Idle timeout in seconds before stop (default: 120)
  RUNPOD_REQUEST_TIMEOUT_SECONDS — Request execution timeout (default: 900)
  RUNPOD_IMAGE_MODEL           — Image model slug (default: black-forest-labs/FLUX.2-klein-4B)
  RUNPOD_VIDEO_MODEL           — Video model slug (default: wan2.2-i2v)
  RUNPOD_COMFYUI_URL           — Base URL for ComfyUI API (default: http://127.0.0.1:8188)
  RUNPOD_API_URL               — Base URL for RunPod GraphQL / Management API (default: https://api.runpod.io/graphql)
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from pathlib import Path

log = logging.getLogger("runpod_config")

# Auto-load .env if present
def _load_env_file():
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val

_load_env_file()


@dataclass
class RunPodConfig:
    """RunPod infrastructure configuration dataclass."""

    endpoint_id: Optional[str] = field(default_factory=lambda: os.getenv("RUNPOD_ENDPOINT_ID"))
    pod_id: Optional[str] = field(default_factory=lambda: os.getenv("RUNPOD_POD_ID"))
    template_id: str = field(default_factory=lambda: os.getenv("RUNPOD_TEMPLATE_ID", "cw3nka7d08"))
    gpu_type: str = field(default_factory=lambda: os.getenv("RUNPOD_GPU_TYPE", "NVIDIA GeForce RTX 4090"))
    volume_id: Optional[str] = field(default_factory=lambda: os.getenv("RUNPOD_VOLUME_ID"))
    network_volume_id: Optional[str] = field(default_factory=lambda: os.getenv("RUNPOD_NETWORK_VOLUME_ID"))

    volume_gb: int = field(default_factory=lambda: int(os.getenv("RUNPOD_VOLUME_GB", "40")))
    container_disk_gb: int = field(default_factory=lambda: int(os.getenv("RUNPOD_CONTAINER_DISK_GB", "20")))

    auto_start: bool = field(default_factory=lambda: os.getenv("RUNPOD_AUTO_START", "true").lower() in ("true", "1", "yes"))
    auto_stop: bool = field(default_factory=lambda: os.getenv("RUNPOD_AUTO_STOP", "true").lower() in ("true", "1", "yes"))
    auto_terminate: bool = field(default_factory=lambda: os.getenv("RUNPOD_AUTO_TERMINATE", "true").lower() in ("true", "1", "yes"))
    model_download_requires_explicit_authorization: bool = field(default_factory=lambda: os.getenv("MODEL_DOWNLOAD_REQUIRES_EXPLICIT_AUTHORIZATION", "true").lower() in ("true", "1", "yes"))


    idle_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("RUNPOD_IDLE_TIMEOUT_SECONDS", os.getenv("RUNPOD_IDLE_TIMEOUT_MINUTES", "2") if os.getenv("RUNPOD_IDLE_TIMEOUT_MINUTES") else "120")))
    max_runtime_minutes: int = field(default_factory=lambda: int(os.getenv("RUNPOD_MAX_RUNTIME_MINUTES", "30")))
    request_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("RUNPOD_REQUEST_TIMEOUT_SECONDS", "900")))

    image_model: str = field(default_factory=lambda: os.getenv("RUNPOD_IMAGE_MODEL", "black-forest-labs/FLUX.2-klein-4B"))
    video_model: str = field(default_factory=lambda: os.getenv("RUNPOD_VIDEO_MODEL", "wan2.2-i2v"))

    comfyui_url: str = field(default_factory=lambda: os.getenv("RUNPOD_COMFYUI_URL", "http://127.0.0.1:8188"))
    api_url: str = field(default_factory=lambda: os.getenv("RUNPOD_API_URL", "https://api.runpod.io/graphql"))


    @property
    def api_key(self) -> Optional[str]:
        """
        Dynamically read API key from os.environ.
        Never store key as an attribute.
        """
        val = os.getenv("RUNPOD_API_KEY", "").strip()
        return val if val else None

    @property
    def is_configured(self) -> bool:
        """True if RUNPOD_API_KEY is present."""
        return bool(self.api_key)

    def summary(self) -> str:
        key_status = "✅ Key configured" if self.is_configured else "❌ No API Key"
        pod_status = f"Pod: {self.pod_id}" if self.pod_id else "No fixed Pod ID"
        return f"RunPodConfig | {key_status} | {pod_status} | AutoStart: {self.auto_start} | AutoStop: {self.auto_stop}"


runpod_config = RunPodConfig()
