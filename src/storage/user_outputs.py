"""
DM AI OS — User Outputs Library (Pachu Local Hub)
=================================================
Manages accessible, user-friendly local output directories on Pachu:
  C:\\Users\\moral\\DM_AI_OS_OUTPUTS\\
  ├── IMAGENES\\
  ├── VIDEOS\\
  ├── AUDIO\\
  ├── UPSCALED\\
  └── LIPSYNC\\

Complements the immutable Auto-Vault by providing instant access to final deliverables.
"""

import os
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

log = logging.getLogger("user_outputs")

DEFAULT_OUTPUTS_ROOT = os.getenv(
    "DM_USER_OUTPUTS_DIR",
    os.path.join(os.path.expanduser("~"), "DM_AI_OS_OUTPUTS")
)

SUBDIRECTORIES = {
    "image": "IMAGENES",
    "video": "VIDEOS",
    "audio": "AUDIO",
    "upscale": "UPSCALED",
    "lipsync": "LIPSYNC",
}


class UserOutputsManager:
    """
    Coordinates user-accessible local deliverable folders on Pachu.
    """

    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = Path(root_dir or DEFAULT_OUTPUTS_ROOT)
        self.ensure_directories()

    def ensure_directories(self) -> Dict[str, str]:
        """Creates the user-facing directories if they do not exist."""
        paths = {}
        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
            for key, folder in SUBDIRECTORIES.items():
                p = self.root_dir / folder
                p.mkdir(parents=True, exist_ok=True)
                paths[key] = str(p)
        except Exception as e:
            log.warning(f"[UserOutputs] Error creating user directories: {e}")
        return paths

    def get_category_folder(self, category: str) -> Path:
        """Returns the specific category folder path."""
        folder_name = SUBDIRECTORIES.get(category.lower(), "IMAGENES")
        target = self.root_dir / folder_name
        target.mkdir(parents=True, exist_ok=True)
        return target

    def categorize_asset(self, filename: str, workflow_name: str = "") -> str:
        """Determines the appropriate user folder based on filename extension and workflow."""
        wf_lower = workflow_name.lower()
        fn_lower = filename.lower()

        if "upscale" in wf_lower or "seedvr" in wf_lower:
            return "upscale"
        if "lipsync" in wf_lower or "float" in wf_lower:
            return "lipsync"
        if "tts" in wf_lower or "audio" in wf_lower or fn_lower.endswith((".wav", ".mp3", ".flac", ".ogg")):
            return "audio"
        if "video" in wf_lower or "wan" in wf_lower or "ltx" in wf_lower or "h3" in wf_lower or fn_lower.endswith((".mp4", ".webm", ".mov", ".avi", ".mkv")):
            return "video"
        return "image"

    def export_asset(
        self,
        vault_file: Path,
        job_id: str,
        workflow_name: str = "",
        model_name: str = ""
    ) -> Tuple[bool, Optional[Path], str]:
        """
        Exports a generated asset from the vault into the user-facing library.
        Preserves SHA-256 and original data.
        """
        if not vault_file.exists():
            return False, None, f"Source vault file not found: {vault_file}"

        cat = self.categorize_asset(vault_file.name, workflow_name)
        target_dir = self.get_category_folder(cat)

        # Build clean user-friendly filename (e.g. SD15_Colab_00001_.png or ZImage_Turbo_c6de537f.png)
        target_path = target_dir / vault_file.name

        try:
            # Copy to user directory (atomic replace if exists)
            shutil.copy2(str(vault_file), str(target_path))
            log.info(f"[UserOutputs] Successfully exported deliverable to {target_path}")
            return True, target_path, "Asset exported to user library"
        except Exception as e:
            log.error(f"[UserOutputs] Failed to copy asset to user folder: {e}")
            return False, None, str(e)

    def list_user_outputs(self, category: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        """Lists recent files in the user output directories."""
        self.ensure_directories()
        results = {}

        cats = [category.lower()] if category and category.lower() in SUBDIRECTORIES else list(SUBDIRECTORIES.keys())

        for c in cats:
            folder = self.get_category_folder(c)
            files = []
            if folder.exists():
                for f in sorted(folder.iterdir(), key=lambda x: x.stat().st_mtime if x.is_file() else 0, reverse=True):
                    if f.is_file() and not f.name.startswith("."):
                        files.append({
                            "filename": f.name,
                            "path": str(f.resolve()),
                            "size_bytes": f.stat().st_size,
                            "modified_at": f.stat().st_mtime
                        })
                        if len(files) >= limit:
                            break
            results[SUBDIRECTORIES[c]] = files

        return {
            "root_dir": str(self.root_dir),
            "categories": results
        }


# Global singleton
user_outputs = UserOutputsManager()
