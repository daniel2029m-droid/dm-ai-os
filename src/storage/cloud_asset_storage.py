"""
DM AI OS — CloudAssetStorage (Google One 5 TB Library Layer)
============================================================
Manages persistent asset storage for the entire creative lifecycle:
  - AI_LIBRARY (Models, weights, checkpoints, VAEs, text encoders, workflows)
  - CHARACTERS (Consistent character sheets, LoRAs, face embeddings)
  - REFERENCES (Style references, poses, visual anchors)
  - GENERATED (Raw high-res outputs from ComfyUI)
  - PUBLISHED (Curated, vaulted, and streamed creative deliverables)

Zero hardcoded credentials. Dynamic OAuth mount via Google Colab / local path override.
"""

import os
import json
import shutil
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

log = logging.getLogger("cloud_asset_storage")

CANONICAL_TREE = [
    "AI_LIBRARY/IMAGE/Z-IMAGE",
    "AI_LIBRARY/IMAGE/FLUX",
    "AI_LIBRARY/IMAGE/SD15",
    "AI_LIBRARY/VIDEO/LTX",
    "AI_LIBRARY/VIDEO/MINIMAX_H3",
    "AI_LIBRARY/UPSCALE/SEEDVR2",
    "AI_LIBRARY/AUDIO/QWEN3_TTS",
    "AI_LIBRARY/LIPSYNC/FLOAT",
    "AI_LIBRARY/TEXT/QWEN",
    "AI_LIBRARY/WORKFLOWS/COMFYUI",
    "CHARACTERS",
    "REFERENCES",
    "GENERATED",
    "PUBLISHED",
]


class CloudAssetStorage:
    """
    Persistent Asset & Model Library coordinator interfacing with Google One 5 TB.
    """

    def __init__(self, root_path: Optional[str] = None):
        if not root_path:
            env_override = os.getenv("DM_DRIVE_MODELS_PATH") or os.getenv("DM_CLOUD_STORAGE_ROOT")
            if env_override:
                root_path = env_override
            elif Path("/content/drive/MyDrive").exists():
                root_path = "/content/drive/MyDrive/DM_AI_OS"
            else:
                # Local development fallback
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                root_path = os.path.join(base_dir, "Project_State", "Storage", "DM_AI_OS")

        self.root_path = Path(root_path)

    def is_mounted(self) -> bool:
        """Returns True if the root storage directory is accessible."""
        try:
            return self.root_path.exists()
        except Exception:
            return False

    def ensure_structure(self) -> Dict[str, bool]:
        """Creates the canonical directory tree if write access is available."""
        results = {}
        try:
            self.root_path.mkdir(parents=True, exist_ok=True)
            for subpath in CANONICAL_TREE:
                target = self.root_path / subpath
                target.mkdir(parents=True, exist_ok=True)
                results[subpath] = target.exists()
        except Exception as e:
            log.warning(f"[CloudAssetStorage] Error ensuring directory structure at {self.root_path}: {e}")
            for subpath in CANONICAL_TREE:
                results[subpath] = (self.root_path / subpath).exists()
        return results

    def get_section_path(self, section: str) -> Path:
        """Resolves full path for a canonical library section."""
        return self.root_path / section

    def find_model_file(self, filename: str, expected_subpath: Optional[str] = None) -> Optional[Path]:
        """
        Searches for a model file across the canonical library.
        If expected_subpath is provided, checks there first.
        """
        if not self.is_mounted():
            return None

        # 1. Check exact subpath if provided
        if expected_subpath:
            direct_candidate = self.root_path / expected_subpath / filename
            if direct_candidate.exists():
                return direct_candidate

        # 2. Check canonical tree locations
        for subpath in CANONICAL_TREE:
            candidate = self.root_path / subpath / filename
            if candidate.exists():
                return candidate

        # 3. Recursive search within AI_LIBRARY
        ai_lib = self.root_path / "AI_LIBRARY"
        if ai_lib.exists():
            for match in ai_lib.rglob(filename):
                if match.is_file():
                    return match

        return None

    def sync_to_worker_cache(
        self,
        source_path: Path,
        cache_dir: Path,
        min_size_bytes: int = 0
    ) -> Tuple[bool, Path, str]:
        """
        Copies a model file from Google Drive storage into local worker cache.
        Skips copying if the cached file already exists with matching size.
        Returns: (success, local_path, message)
        """
        if not source_path.exists():
            return False, source_path, f"Source file does not exist: {source_path}"

        cache_dir.mkdir(parents=True, exist_ok=True)
        dest_path = cache_dir / source_path.name

        source_size = source_path.stat().st_size
        if min_size_bytes > 0 and source_size < min_size_bytes:
            return False, dest_path, f"Source file size ({source_size}) below minimum ({min_size_bytes})"

        # Check existing cache hit
        if dest_path.exists():
            cached_size = dest_path.stat().st_size
            if cached_size == source_size:
                log.info(f"[CloudAssetStorage] Cache HIT for {source_path.name} at {dest_path}")
                return True, dest_path, "Cache hit (matching size)"

        # Copy with progress logging
        try:
            log.info(f"[CloudAssetStorage] Copying {source_path.name} ({source_size / (1024**3):.2f} GB) to cache...")
            shutil.copy2(str(source_path), str(dest_path))
            return True, dest_path, "Copied to worker cache successfully"
        except Exception as e:
            log.error(f"[CloudAssetStorage] Copy failed: {e}")
            return False, dest_path, f"Copy error: {e}"

    def vault_generated_output(
        self,
        source_file: Path,
        job_id: str,
        category: str = "GENERATED"
    ) -> Tuple[bool, Optional[str]]:
        """
        Saves a generated asset into the persistent Google Drive storage library.
        Returns: (success, persistent_path_str)
        """
        if not source_file.exists():
            return False, None

        dest_dir = self.root_path / category / job_id
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / source_file.name
            shutil.copy2(str(source_file), str(dest_file))
            log.info(f"[CloudAssetStorage] Vaulted output to {dest_file}")
            return True, str(dest_file)
        except Exception as e:
            log.warning(f"[CloudAssetStorage] Could not vault output to persistent storage: {e}")
            return False, None

    def get_storage_diagnostics(self) -> Dict[str, Any]:
        """Provides non-destructive storage metrics."""
        diag = {
            "root_path": str(self.root_path),
            "is_mounted": self.is_mounted(),
            "sections": {},
            "total_models_found": 0,
            "storage_gb": "unknown"
        }

        if not self.is_mounted():
            return diag

        for subpath in CANONICAL_TREE:
            p = self.root_path / subpath
            exists = p.exists()
            file_count = len(list(p.iterdir())) if exists else 0
            diag["sections"][subpath] = {"exists": exists, "file_count": file_count}

        try:
            total, used, free = shutil.disk_usage(str(self.root_path))
            diag["storage_gb"] = {
                "total": round(total / (1024**3), 1),
                "used": round(used / (1024**3), 1),
                "free": round(free / (1024**3), 1)
            }
        except Exception:
            pass

        return diag


# Global singleton
cloud_asset_storage = CloudAssetStorage()
