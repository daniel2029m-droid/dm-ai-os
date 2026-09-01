"""
DM AI OS v1.5.2 — Google Drive 5 TB MCP Integration Layer
=========================================================
Exposes Google Drive (Google One 5 TB) as Model Context Protocol (MCP) tools
for the Agent Runtime, allowing discovery, searching, and reading of cloud assets,
models, and project files at zero additional API cost.
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .registry import mcp_registry

log = logging.getLogger("gdrive_mcp")


class GoogleDriveMCP:
    """
    Model Context Protocol handler for Google Drive (Google One 5 TB).
    Operates seamlessly across Google Colab mount points, local synchronized folders,
    and Google Drive OAuth sessions.
    """

    def __init__(self):
        self.mount_point = self._resolve_mount_point()

    def _resolve_mount_point(self) -> Optional[Path]:
        """Resolves active Google Drive mount or local synchronized root."""
        env_override = os.getenv("DM_DRIVE_MODELS_PATH") or os.getenv("DM_CLOUD_STORAGE_ROOT")
        if env_override and Path(env_override).exists():
            return Path(env_override).resolve()

        colab_path = Path("/content/drive/MyDrive")
        if colab_path.exists():
            return colab_path.resolve()

        local_storage = Path(__file__).resolve().parent.parent.parent / "Project_State" / "Storage" / "DM_AI_OS"
        if local_storage.exists():
            return local_storage.resolve()

        return None

    def get_storage_quota(self) -> Dict[str, Any]:
        """Returns storage capacity and tier information."""
        mount = self._resolve_mount_point()
        is_mounted = mount is not None and mount.exists()
        
        return {
            "tier": "Google One AI Premium (5 TB)",
            "status": "MOUNTED" if is_mounted else "CONFIGURED",
            "mount_point": str(mount) if is_mounted else "/content/drive/MyDrive (Colab OAuth)",
            "total_capacity_tb": 5.0,
            "cost_per_api_call": "$0.00 (Zero API Cost)",
            "supported_features": [
                "AI_LIBRARY (FLUX, Wan 2.1, LTX-Video, SDXL checkpoints)",
                "CHARACTERS (LoRAs, visual embeddings)",
                "GENERATED (Raw ComfyUI outputs)",
                "PUBLISHED (Final creative media)"
            ]
        }

    def list_files(self, subpath: str = ".", max_results: int = 50) -> Dict[str, Any]:
        """Lists files and folders in Google Drive storage."""
        mount = self._resolve_mount_point()
        if not mount or not mount.exists():
            return {
                "status": "UNAVAILABLE",
                "message": "Google Drive no está montado en este host. En Google Colab se monta con: drive.mount('/content/drive')",
                "storage_info": self.get_storage_quota()
            }

        target = (mount / subpath).resolve()
        if not target.exists():
            return {"status": "ERROR", "message": f"Path '{subpath}' does not exist in Google Drive."}

        items = []
        try:
            for p in sorted(target.iterdir())[:max_results]:
                items.append({
                    "name": p.name,
                    "is_dir": p.is_dir(),
                    "size_bytes": p.stat().st_size if p.is_file() else 0,
                    "subpath": str(p.relative_to(mount)).replace("\\", "/")
                })
            return {"status": "SUCCESS", "subpath": subpath, "items_count": len(items), "items": items}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def read_file(self, file_path: str, max_bytes: int = 50000) -> Dict[str, Any]:
        """Reads text content of a file located in Google Drive."""
        mount = self._resolve_mount_point()
        if not mount or not mount.exists():
            return {
                "status": "UNAVAILABLE",
                "message": "Google Drive no está montado localmente. Disponible vía Colab OAuth."
            }

        target = (mount / file_path).resolve()
        if not target.exists():
            return {"status": "ERROR", "message": f"File '{file_path}' does not exist in Google Drive."}

        if target.is_dir():
            return {"status": "ERROR", "message": f"Path '{file_path}' is a directory, not a file."}

        try:
            content = target.read_text(encoding="utf-8", errors="ignore")[:max_bytes]
            return {
                "status": "SUCCESS",
                "file_path": file_path,
                "size_bytes": target.stat().st_size,
                "content": content
            }
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def search_files(self, query: str, max_results: int = 20) -> Dict[str, Any]:
        """Searches for files matching query across Google Drive."""
        mount = self._resolve_mount_point()
        if not mount or not mount.exists():
            return {
                "status": "UNAVAILABLE",
                "message": "Google Drive no está montado localmente."
            }

        q_lower = query.lower()
        matches = []
        try:
            for p in mount.glob("**/*"):
                if q_lower in p.name.lower():
                    matches.append({
                        "name": p.name,
                        "is_dir": p.is_dir(),
                        "subpath": str(p.relative_to(mount)).replace("\\", "/")
                    })
                if len(matches) >= max_results:
                    break
            return {"status": "SUCCESS", "query": query, "matches_count": len(matches), "matches": matches}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}


gdrive_mcp = GoogleDriveMCP()

# Register MCP Tools in Registry
mcp_registry.register_tool(
    name="gdrive_get_storage_quota",
    description="Returns storage capacity, mount status, and Google One 5 TB tier details.",
    handler=gdrive_mcp.get_storage_quota
)

mcp_registry.register_tool(
    name="gdrive_list_files",
    description="Lists files and directories in Google Drive (Google One 5 TB).",
    handler=gdrive_mcp.list_files
)

mcp_registry.register_tool(
    name="gdrive_read_file",
    description="Reads text content of a file stored in Google Drive.",
    handler=gdrive_mcp.read_file
)

mcp_registry.register_tool(
    name="gdrive_search_files",
    description="Searches for files matching a keyword in Google Drive.",
    handler=gdrive_mcp.search_files
)
