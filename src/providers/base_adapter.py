"""
DM AI OS — Base Provider Adapter & Enums
Defines core interfaces without circular dependencies.
"""
import os
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

class ProviderStatus(str, Enum):
    AVAILABLE    = "available"
    UNAVAILABLE  = "unavailable"
    AUTH_EXPIRED = "auth_expired"
    NO_CREDITS   = "no_credits"
    DISABLED     = "disabled"
    UNKNOWN      = "unknown"

class ProviderCapability(str, Enum):
    CHAT            = "chat"
    IMAGE           = "image"
    VIDEO           = "video"
    CODE            = "code"
    AUDIO           = "audio"
    LOCAL           = "local"
    CHARACTER_MGMT  = "character_management"
    JOB_STATUS      = "job_status"
    ASSET_RETRIEVAL = "asset_retrieval"

class BaseProviderAdapter:
    """All provider adapters must inherit from this."""
    id: str = "base"
    display_name: str = "Base Provider"
    capabilities: List[ProviderCapability] = []
    is_local: bool = False

    async def health_check(self) -> Tuple[ProviderStatus, float, str]:
        """Returns (status, latency_ms, account_info)."""
        raise NotImplementedError

    async def chat(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        raise NotImplementedError

    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError

    async def generate_video(self, prompt: str, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError

    async def trigger_login(self) -> Dict[str, Any]:
        return {"status": "not_supported", "message": f"{self.display_name} login not implemented"}

    async def logout(self) -> Dict[str, Any]:
        return {"status": "not_supported", "message": f"{self.display_name} logout not implemented"}

    def get_account_info(self) -> str:
        return "Unknown"

    def is_configured(self) -> bool:
        if self.is_local:
            return True
        if hasattr(self, "api_key"):
            return bool(str(getattr(self, "api_key") or "").strip())
        if hasattr(self, "_env_key"):
            return bool(os.getenv(getattr(self, "_env_key"), "").strip())
        return False
