"""
NVIDIA NIM — Central Configuration for DM AI OS
=================================================
Reads all values from environment variables.
NEVER hardcode API keys or credentials in this file.

Environment variables:
  NVIDIA_API_KEY          — NVIDIA NIM API key (NVAPI token)
  NVIDIA_IMAGE_MODEL      — Target model (default: black-forest-labs/flux.2-klein-4b)
  NVIDIA_IMAGE_BASE_URL   — NIM Endpoint URL
  NVIDIA_DEFAULT_TIMEOUT  — Default request timeout in seconds (default: 60.0)
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path

log = logging.getLogger("nvidia_config")

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


NVIDIA_DEFAULT_MODEL = "black-forest-labs/flux.2-klein-4b"
NVIDIA_DEFAULT_BASE_URL = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.2-klein-4b"

SUPPORTED_ASPECT_RATIOS = {
    "1:1":  (1024, 1024),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "4:5":  (896, 1120),
    "5:4":  (1120, 896),
    "3:2":  (1216, 812),
    "2:3":  (812, 1216),
}

SUPPORTED_IMAGE_FORMATS = {"png", "jpg", "jpeg"}

@dataclass
class NVIDIAConfig:
    """NVIDIA NIM configuration dataclass."""

    model: str = field(default_factory=lambda: os.getenv(
        "NVIDIA_IMAGE_MODEL", NVIDIA_DEFAULT_MODEL
    ))

    base_url: str = field(default_factory=lambda: os.getenv(
        "NVIDIA_IMAGE_BASE_URL", NVIDIA_DEFAULT_BASE_URL
    ))

    timeout: float = field(default_factory=lambda: float(os.getenv(
        "NVIDIA_DEFAULT_TIMEOUT", "60.0"
    )))

    @property
    def api_key(self) -> Optional[str]:
        """
        Retrieves API key dynamically from environment.
        Never stores the key in memory or attributes.
        """
        val = os.getenv("NVIDIA_API_KEY", "").strip()
        return val if val else None

    @property
    def is_configured(self) -> bool:
        """True if NVIDIA API Key is present in environment."""
        return bool(self.api_key)

    def get_dimensions_for_ratio(self, aspect_ratio: str) -> tuple:
        """Map aspect ratio string (e.g. '16:9') to (width, height). Defaults to 1024x1024."""
        return SUPPORTED_ASPECT_RATIOS.get(aspect_ratio, (1024, 1024))

    def summary(self) -> str:
        key_status = "✅ Key set" if self.is_configured else "❌ No key"
        return f"NVIDIAConfig | Model: {self.model} | BaseURL: {self.base_url} | {key_status}"


nvidia_config = NVIDIAConfig()
