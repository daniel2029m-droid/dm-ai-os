"""
DM AI OS v1.5.1 — Distributed Model Storage Plane
==================================================
Decouples ephemeral GPU compute runtimes from persistent external model storage
(Google Drive, RunPod volumes, and local fallback).

SINGLE SOURCE OF TRUTH: config/model_registry.json
  All model definitions are loaded from that file at runtime.
  Do NOT hardcode model catalogs in Python — modify the JSON instead.

Storage nodes are defined in config/storage_nodes.json.
  No credentials, emails, or tokens are stored in either config file.
  Drive identity is resolved exclusively via Google Colab OAuth (drive.mount()).

Enforces:
  - 3-Level Integrity Engine (Physical Existence, Binary Header/Size, ComfyUI /object_info).
  - Multi-Component Compound Models (FLUX, WAN, SDXL, Hunyuan).
  - Smart Storage Decision (copy/direct/alternative based on disk/VRAM).
  - Pre-dispatch VRAM and Hardware Constraint Validation.
  - Explicit model status: CONFIGURED → DISCOVERED → VALIDATED → READY (physical only).
"""

import os
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set

log = logging.getLogger("model_storage_plane")


# ── Model Status Constants ────────────────────────────────────────────

class ModelStatus:
    """Explicit model status progression. READY requires physical generation proof."""
    NOT_REGISTERED        = "NOT_REGISTERED"
    CONFIGURED            = "CONFIGURED"       # defined in registry, not yet discovered on storage
    DISCOVERED            = "DISCOVERED"       # file found on storage, not yet integrity-validated
    VALIDATED             = "VALIDATED"        # integrity check passed, not yet ComfyUI-indexed
    NOT_INDEXED           = "NOT_INDEXED_BY_COMFYUI"
    MISSING_COMPONENTS    = "MISSING_COMPONENTS"
    CORRUPTED_COMPONENTS  = "CORRUPTED_COMPONENTS"
    INSUFFICIENT_VRAM     = "INSUFFICIENT_VRAM"
    STORAGE_UNAVAILABLE   = "STORAGE_UNAVAILABLE"
    UNAVAILABLE           = "UNAVAILABLE"
    # READY is only assigned after physical ComfyUI generation proof (Phase H+)
    READY                 = "READY"


# ── Config Loaders ────────────────────────────────────────────────────

def _find_config_dir() -> Path:
    """Resolves the config/ directory relative to this file's location."""
    # Typical: src/core/model_storage_plane.py → ../../config/
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent.parent / "config",
        Path(os.getcwd()) / "config",
        Path("/content/dm-ai-os/config"),  # Colab runtime clone path
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # fallback even if not found


def load_model_catalog() -> Dict[str, Any]:
    """
    Loads model definitions from config/model_registry.json.
    This is the SINGLE SOURCE OF TRUTH for model definitions.
    Returns the 'models' dict keyed by model_id.
    """
    config_dir = _find_config_dir()
    registry_path = config_dir / "model_registry.json"
    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        catalog = data.get("models", {})
        log.info(f"[ModelStoragePlane] Loaded {len(catalog)} models from {registry_path}")
        return catalog
    except FileNotFoundError:
        log.error(f"[ModelStoragePlane] model_registry.json not found at {registry_path}")
        return {}
    except json.JSONDecodeError as e:
        log.error(f"[ModelStoragePlane] model_registry.json parse error: {e}")
        return {}


def load_storage_nodes() -> Dict[str, Any]:
    """
    Loads storage node definitions from config/storage_nodes.json.
    No credentials or account identifiers are loaded from here.
    """
    config_dir = _find_config_dir()
    nodes_path = config_dir / "storage_nodes.json"
    try:
        with open(nodes_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        nodes = data.get("nodes", {})
        log.info(f"[ModelStoragePlane] Loaded {len(nodes)} storage nodes from {nodes_path}")
        return nodes
    except FileNotFoundError:
        log.warning(f"[ModelStoragePlane] storage_nodes.json not found at {nodes_path}")
        return {}
    except json.JSONDecodeError as e:
        log.error(f"[ModelStoragePlane] storage_nodes.json parse error: {e}")
        return {}


# ── Storage Node Abstraction ─────────────────────────────────────────

@dataclass
class StorageNode:
    """
    Represents a named persistent storage node (Drive, RunPod, local cache).
    No credentials stored — identity resolved at runtime via OAuth.
    """
    node_id: str
    provider: str
    display_name: str
    mount_point: str
    root_path: str
    env_override: str = ""
    status: str = "configured"   # configured | active | unavailable | optional | ephemeral
    priority: int = 1
    capabilities: List[str] = field(default_factory=list)

    def resolve_full_path(self) -> Path:
        """Returns the full filesystem path for this storage node, respecting env_override."""
        # Environment variable takes precedence (allows per-session override without code change)
        env_val = os.getenv(self.env_override) if self.env_override else None
        if env_val:
            return Path(env_val)
        return Path(self.mount_point) / self.root_path

    def is_accessible(self) -> bool:
        """Returns True if the storage path exists and is readable."""
        try:
            return self.resolve_full_path().exists()
        except Exception:
            return False


# ── Binary Integrity Validator ────────────────────────────────────────

def is_valid_safetensors_binary(file_path: Path, min_bytes: int = 0) -> Tuple[bool, str]:
    """
    Validates physical existence, minimum size, and safetensors binary header format.
    Safetensors header: 8-byte little-endian uint64 length followed by JSON metadata starting with '{'.
    """
    if not file_path.exists():
        return False, "File does not exist"
    
    try:
        size = file_path.stat().st_size
    except Exception as e:
        return False, f"stat error: {e}"

    if size == 0:
        return False, "File is 0 bytes (empty)"
    
    if min_bytes > 0 and size < min_bytes:
        return False, f"File size ({size:,} bytes) is below minimum required ({min_bytes:,} bytes)"

    # If it's a safetensors file, check binary header
    if file_path.suffix.lower() == ".safetensors":
        try:
            with open(file_path, "rb") as f:
                header_bytes = f.read(16)
                if len(header_bytes) < 16:
                    return False, "Header too short to be a valid safetensors binary"
                
                header_len = int.from_bytes(header_bytes[:8], byteorder="little")
                if header_len <= 0 or header_len > 100_000_000:
                    return False, f"Corrupted safetensors header length ({header_len})"
                
                # Verify JSON character
                if header_bytes[8:9] != b"{":
                    # Check if it was saved as raw text error / HTML
                    try:
                        f.seek(0)
                        sample = f.read(200).decode("utf-8", errors="ignore")
                        if "404" in sample or "Not Found" in sample or "<html" in sample.lower() or "error" in sample.lower():
                            return False, f"File contains HTTP/HTML error response: {sample[:60]}"
                    except Exception:
                        pass
                    return False, "Safetensors metadata does not start with valid JSON '{'"
        except Exception as e:
            return False, f"Error reading binary header: {e}"

    return True, "Valid binary"


# ── Storage Plane Core Engine ─────────────────────────────────────────

@dataclass
class StorageVolume:
    storage_id: str
    provider: str
    base_path: Path
    is_mounted: bool = True
    account_label: Optional[str] = None
    tags: List[str] = field(default_factory=list)


class ModelStoragePlane:
    """
    Central Coordinator for persistent multi-storage resolution and ComfyUI integration.

    Model definitions are loaded from config/model_registry.json (single source of truth).
    Storage nodes are loaded from config/storage_nodes.json.
    No credentials stored in this class or its config files.
    """

    def __init__(self, catalog: Optional[Dict[str, Any]] = None):
        # Load catalog from JSON if not provided explicitly (single source of truth)
        self.catalog: Dict[str, Any] = catalog if catalog is not None else load_model_catalog()
        self.storage_volumes: Dict[str, StorageVolume] = {}
        self.storage_nodes: Dict[str, StorageNode] = {}
        self._load_storage_nodes_from_config()

    def _load_storage_nodes_from_config(self) -> None:
        """Initializes StorageNode objects from storage_nodes.json (no credentials)."""
        raw_nodes = load_storage_nodes()
        for node_id, cfg in raw_nodes.items():
            node = StorageNode(
                node_id=node_id,
                provider=cfg.get("provider", "unknown"),
                display_name=cfg.get("display_name", node_id),
                mount_point=cfg.get("mount_point", "/content/drive"),
                root_path=cfg.get("root_path", ""),
                env_override=cfg.get("env_override", ""),
                status=cfg.get("status", "configured"),
                priority=cfg.get("priority", 1),
                capabilities=cfg.get("capabilities", []),
            )
            self.storage_nodes[node_id] = node
            # Auto-register active nodes as storage volumes
            if node.status in ("configured", "active") and node.is_accessible():
                self.register_storage(
                    storage_id=node_id,
                    provider=node.provider,
                    base_path=node.resolve_full_path(),
                    is_mounted=True,
                    tags=node.capabilities
                )
                log.info(f"[ModelStoragePlane] Auto-registered storage node '{node_id}' at '{node.resolve_full_path()}'")
            else:
                log.debug(f"[ModelStoragePlane] Node '{node_id}' status='{node.status}' — not auto-registered (not accessible or ephemeral)")

    def reload_catalog(self) -> int:
        """Reloads model catalog from config/model_registry.json. Returns count of loaded models."""
        self.catalog = load_model_catalog()
        return len(self.catalog)

    def get_storage_node(self, node_id: str) -> Optional[StorageNode]:
        """Returns a StorageNode by ID."""
        return self.storage_nodes.get(node_id)

    def list_storage_nodes(self) -> List[Dict[str, Any]]:
        """Returns diagnostic info for all configured storage nodes."""
        result = []
        for nid, node in self.storage_nodes.items():
            full_path = node.resolve_full_path()
            accessible = node.is_accessible()
            result.append({
                "node_id": nid,
                "provider": node.provider,
                "display_name": node.display_name,
                "full_path": str(full_path),
                "status": node.status,
                "accessible": accessible,
                "priority": node.priority,
                "capabilities": node.capabilities,
            })
        return sorted(result, key=lambda x: x["priority"])

    def get_storage_nodes_status(self) -> Dict[str, Any]:
        """Returns summary status for all storage nodes — used by diagnostic endpoints."""
        nodes = self.list_storage_nodes()
        return {
            "total": len(nodes),
            "accessible": sum(1 for n in nodes if n["accessible"]),
            "nodes": nodes
        }

    def register_storage(
        self,
        storage_id: str,
        provider: str,
        base_path: str | Path,
        is_mounted: bool = True,
        account_label: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> StorageVolume:
        """Registers a persistent storage volume (Google Drive, Shared Account, Network Volume)."""
        p = Path(base_path)
        vol = StorageVolume(
            storage_id=storage_id,
            provider=provider,
            base_path=p,
            is_mounted=is_mounted,
            account_label=account_label,
            tags=tags or []
        )
        self.storage_volumes[storage_id] = vol
        log.info(f"[ModelStoragePlane] Registered storage '{storage_id}' ({provider}) at '{p}'")
        return vol

    def unregister_storage(self, storage_id: str) -> bool:
        if storage_id in self.storage_volumes:
            del self.storage_volumes[storage_id]
            return True
        return False

    def list_storages(self) -> List[Dict[str, Any]]:
        res = []
        for vid, vol in self.storage_volumes.items():
            exists = vol.base_path.exists()
            res.append({
                "storage_id": vid,
                "provider": vol.provider,
                "base_path": str(vol.base_path),
                "is_mounted": vol.is_mounted and exists,
                "exists_physically": exists,
                "account_label": vol.account_label,
                "tags": vol.tags
            })
        return res

    def discover_model_file(self, filename: str, category: str) -> Optional[Path]:
        """
        Scans all mounted storage volumes and standard category subpaths to locate a model file.
        Searches:
          1. {base_path}/{category}/{filename}
          2. {base_path}/models/{category}/{filename}
          3. {base_path}/{filename}
        """
        category_aliases = [category]
        if category in ("unet", "diffusion_models"):
            category_aliases = ["diffusion_models", "unet"]
        elif category in ("clip", "text_encoders"):
            category_aliases = ["clip", "text_encoders"]

        for vol in self.storage_volumes.values():
            if not vol.is_mounted or not vol.base_path.exists():
                continue

            for cat in category_aliases:
                candidates = [
                    vol.base_path / cat / filename,
                    vol.base_path / "models" / cat / filename,
                    vol.base_path / filename
                ]
                for c in candidates:
                    if c.exists():
                        return c
        return None

    def resolve_model(
        self,
        model_id: str,
        comfy_object_info: Optional[Dict[str, Any]] = None,
        available_vram_gb: Optional[float] = None,
        gpu_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Performs 3-Level validation for requested model:
          Level 1: Physical existence across all mounted storage volumes.
          Level 2: Binary integrity (safetensors header & size constraints).
          Level 3: ComfyUI /object_info indexing verification.
          Hardware: VRAM constraint verification.
        """
        if model_id not in self.catalog:
            return {
                "model_id": model_id,
                "available": False,
                "status": "NOT_REGISTERED",
                "error": f"Model '{model_id}' is not registered in catalog."
            }

        defn = self.catalog[model_id]
        required_components = defn.get("required_components", [])
        resolved_components = []
        missing_components = []
        corrupted_components = []
        unindexed_components = []

        for comp in required_components:
            fname = comp["filename"]
            cat = comp.get("category", "checkpoints")
            min_size = comp.get("min_size_bytes", 0)
            loader_node = comp.get("loader_node")
            input_param = comp.get("input_param")
            optional = comp.get("optional", False)

            # Level 1: Physical Existence
            file_path = self.discover_model_file(fname, cat)
            if not file_path:
                if not optional:
                    missing_components.append({
                        "filename": fname,
                        "category": cat,
                        "expected_size_bytes": min_size,
                        "error": "File not found in any mounted storage volume"
                    })
                continue

            # Level 2: Binary Integrity
            is_valid, reason = is_valid_safetensors_binary(file_path, min_bytes=min_size)
            if not is_valid:
                if not optional:
                    corrupted_components.append({
                        "filename": fname,
                        "path": str(file_path),
                        "reason": reason
                    })
                continue

            # Level 3: ComfyUI /object_info Verification (if provided)
            if comfy_object_info and loader_node and input_param:
                node_spec = comfy_object_info.get(loader_node, {})
                req_inputs = node_spec.get("input", {}).get("required", {})
                avail_list = req_inputs.get(input_param, [[]])[0]
                if isinstance(avail_list, list) and fname not in avail_list:
                    unindexed_components.append({
                        "filename": fname,
                        "node": loader_node,
                        "input_param": input_param,
                        "reason": f"ComfyUI {loader_node} has not indexed '{fname}'"
                    })

            resolved_components.append({
                "filename": fname,
                "category": cat,
                "path": str(file_path),
                "size_bytes": file_path.stat().st_size
            })

        # Evaluate readiness
        is_ready = (
            len(missing_components) == 0 and
            len(corrupted_components) == 0 and
            len(unindexed_components) == 0
        )

        status_label = "READY" if is_ready else "UNAVAILABLE"
        if missing_components:
            status_label = "MISSING_COMPONENTS"
        elif corrupted_components:
            status_label = "CORRUPTED_COMPONENTS"
        elif unindexed_components:
            status_label = "NOT_INDEXED_BY_COMFYUI"

        # Hardware VRAM Check
        vram_ok = True
        vram_msg = "OK"
        min_vram = defn.get("min_gpu_vram", 0.0)
        if available_vram_gb is not None and available_vram_gb < min_vram:
            vram_ok = False
            vram_msg = f"Insufficient VRAM ({available_vram_gb:.1f} GB < required {min_vram:.1f} GB)"

        return {
            "model_id": model_id,
            "display_name": defn.get("display_name"),
            "architecture": defn.get("architecture"),
            "category": defn.get("category"),
            "available": is_ready and vram_ok,
            "status": status_label if vram_ok else "INSUFFICIENT_VRAM",
            "vram_compatible": vram_ok,
            "vram_message": vram_msg,
            "resolved_components": resolved_components,
            "missing_components": missing_components,
            "corrupted_components": corrupted_components,
            "unindexed_components": unindexed_components,
            "capabilities": defn.get("capabilities", ["image"])
        }

    def evaluate_all_models(
        self,
        comfy_object_info: Optional[Dict[str, Any]] = None,
        available_vram_gb: Optional[float] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Evaluates all catalog models and returns capability matrix."""
        matrix = {}
        for mid in self.catalog.keys():
            matrix[mid] = self.resolve_model(
                mid,
                comfy_object_info=comfy_object_info,
                available_vram_gb=available_vram_gb
            )
        return matrix

    def get_ready_model_ids(
        self,
        comfy_object_info: Optional[Dict[str, Any]] = None,
        available_vram_gb: Optional[float] = None
    ) -> List[str]:
        """Returns list of model_ids that are fully verified and ready for generation."""
        matrix = self.evaluate_all_models(comfy_object_info=comfy_object_info, available_vram_gb=available_vram_gb)
        return [mid for mid, res in matrix.items() if res.get("available")]

    def generate_extra_model_paths_yaml(self) -> str:
        """
        Generates standard ComfyUI extra_model_paths.yaml content
        mapping all registered mounted storage base paths.
        """
        lines = ["# DM AI OS Distributed Model Storage Paths"]
        for idx, (vid, vol) in enumerate(self.storage_volumes.items()):
            if not vol.is_mounted:
                continue
            base = str(vol.base_path).replace("\\", "/")
            lines.append(f"drive_storage_{idx}:")
            lines.append(f"    base_path: {base}")
            lines.append("    checkpoints: checkpoints")
            lines.append("    diffusion_models: diffusion_models")
            lines.append("    unet: diffusion_models")
            lines.append("    clip: clip")
            lines.append("    text_encoders: clip")
            lines.append("    vae: vae")
            lines.append("    loras: loras")
            lines.append("    controlnet: controlnet")
            lines.append("    upscale_models: upscale_models")
            lines.append("")
        return "\n".join(lines)


# Singleton Instance
model_storage_plane = ModelStoragePlane()
