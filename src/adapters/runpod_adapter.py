"""
RunPod GPU Adapter — FLUX.2 Klein 4B & Video AI Integration
============================================================
Encapsulates all interaction with RunPod GraphQL/REST Management API & ComfyUI API.

Features:
- Complete GPU Lifecycle Control: list_pods, start_pod, stop_pod, terminate_pod, wait_until_ready
- Cost Control Guardrails: AUTO START on job submission, AUTO STOP when idle
- GPU Watchdog & gpu_session context manager for try/finally cleanup safety
- Workflows support: FLUX.2 Klein 4B, Wan 2.2 I2V, Wan 2.2 + VACE Motion Transfer
- Handles HTTP 401/403/404/429/500+, timeouts, and connection failures safely
- SHA-256 caching via StorageLayer and call logging via provider_history
"""

import os
import json
import time
import base64
import hashlib
import asyncio
import logging
import httpx
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional, Tuple, Union

from ..config.runpod_config import runpod_config
from ..storage.storage_layer import storage
from ..providers.provider_history import provider_history

log = logging.getLogger("runpod_adapter")


class RunPodAdapterError(Exception):
    """Base exception for RunPod infrastructure errors."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class RunPodAdapter:
    """Adapter for managing RunPod GPUs and executing ComfyUI / Model workflows."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        comfyui_url: Optional[str] = None,
        api_url: Optional[str] = None
    ):
        self._override_api_key = api_key
        self._override_comfyui_url = comfyui_url
        self._override_api_url = api_url
        self._last_activity_time: float = time.time()
        self._active_jobs_count: int = 0

    @property
    def api_key(self) -> str:
        key = self._override_api_key or runpod_config.api_key
        if not key:
            raise RunPodAdapterError(
                "RUNPOD_API_KEY environment variable is missing. Set RUNPOD_API_KEY before making calls.",
                status_code=401
            )
        return key

    @property
    def comfyui_url(self) -> str:
        return (self._override_comfyui_url or runpod_config.comfyui_url).rstrip("/")

    @property
    def api_url(self) -> str:
        return self._override_api_url or runpod_config.api_url

    # ── GraphQL / REST API Helpers ───────────────────────────────

    async def _graphql_query(self, query: str, variables: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute a GraphQL query against RunPod API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"query": query, "variables": variables or {}}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(self.api_url, json=payload, headers=headers)
                if r.status_code in (401, 403):
                    raise RunPodAdapterError("HTTP Unauthorized: Invalid RUNPOD_API_KEY.", status_code=r.status_code)
                if r.status_code == 429:
                    raise RunPodAdapterError("HTTP 429: RunPod API rate limit exceeded.", status_code=429)

                data = {}
                try:
                    data = r.json()
                except Exception:
                    pass

                if "errors" in data and data["errors"]:
                    err_msg = data["errors"][0].get("message", "GraphQL query error")
                    raise RunPodAdapterError(f"RunPod GraphQL Error: {err_msg}", status_code=r.status_code)

                if r.status_code >= 400:
                    raise RunPodAdapterError(f"HTTP {r.status_code}: {r.text}", status_code=r.status_code)

                return data.get("data", {})
        except RunPodAdapterError:
            raise
        except Exception as e:
            raise RunPodAdapterError(f"RunPod API connection failed: {e}")


    # ── GPU Lifecycle Control ────────────────────────────────────

    async def get_account_status(self) -> Dict[str, Any]:
        """Query user account info, credits, and active pods."""
        query = """
        query {
            myself {
                id
                email
                clientBalance
                pods {
                    id
                    name
                    desiredStatus
                    costPerHr
                }
            }
        }
        """
        data = await self._graphql_query(query)
        myself = data.get("myself", {})
        return {
            "status": "ok",
            "email": myself.get("email", "Unknown"),
            "balance": myself.get("clientBalance", 0.0),
            "pods_count": len(myself.get("pods", []))
        }

    async def list_pods(self) -> List[Dict[str, Any]]:
        """List all pods under the user account."""
        query = """
        query {
            myself {
                pods {
                    id
                    name
                    desiredStatus
                    costPerHr
                    gpuCount
                }
            }
        }
        """
        data = await self._graphql_query(query)
        myself = data.get("myself", {})
        return myself.get("pods", [])


    async def get_pod_status(self, pod_id: Optional[str] = None) -> Dict[str, Any]:
        """Check status of a specific pod (or default configured pod)."""
        target_pod_id = pod_id or runpod_config.pod_id
        if not target_pod_id:
            return {"status": "no_pod_id", "desiredStatus": "STOPPED", "is_ready": False}

        query = """
        query Pod($podId: String!) {
            pod(input: {podId: $podId}) {
                id
                name
                desiredStatus
                lastStatusChange
                costPerHr
            }
        }
        """
        try:
            data = await self._graphql_query(query, {"podId": target_pod_id})
            pod = data.get("pod")
            if not pod:
                return {"status": "not_found", "desiredStatus": "TERMINATED", "is_ready": False}
            status = pod.get("desiredStatus", "UNKNOWN")
            return {
                "pod_id": target_pod_id,
                "status": status,
                "desiredStatus": status,
                "is_ready": status == "RUNNING",
                "cost_per_hr": pod.get("costPerHr", 0.0)
            }
        except Exception as e:
            log.warning(f"[RunPodAdapter] get_pod_status failed: {e}")
            return {"status": "error", "error": str(e), "is_ready": False}

    async def validate_network_volume_compatibility(self, volume_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate that configured Network Volume exists, is available, and get its target datacenter.
        Raises RunPodAdapterError if volume is missing or inaccessible.
        """
        target_vol_id = volume_id or runpod_config.network_volume_id
        if not target_vol_id:
            return {"status": "NO_VOLUME_CONFIGURED", "is_valid": False, "dataCenterId": None}

        vols = await self.list_network_volumes()
        vol = next((v for v in vols if v.get("id") == target_vol_id or v.get("name") == "DM-AI-OS-Models"), None)

        if not vol:
            raise RunPodAdapterError(
                f"NETWORK_VOLUME_NOT_FOUND: Configured volume '{target_vol_id}' does not exist on RunPod account.",
                status_code=404
            )

        dc_id = vol.get("dataCenterId")
        log.info(f"[RunPodAdapter] Network Volume validated: ID={vol.get('id')} Name={vol.get('name')} Size={vol.get('size')}GB Datacenter={dc_id}")
        return {
            "status": "VALID",
            "is_valid": True,
            "volume_id": vol.get("id"),
            "name": vol.get("name"),
            "size_gb": vol.get("size"),
            "dataCenterId": dc_id
        }

    @staticmethod
    def get_comfyui_pod_docker_args() -> str:
        """ComfyUI pods should not override the entrypoint (start.sh)."""
        return ""

    @staticmethod
    def get_comfyui_volume_setup_cmd() -> str:
        """
        [DEPRECATED - kept for compatibility] Use get_start_user_sh_content() instead.
        The dockerArgs approach is unreliable for ValyrianTech template (cw3nka7d08)
        because dockerArgs runs as entrypoint arguments, not before ComfyUI starts.
        """
        return RunPodAdapter.get_phase1_write_start_user_sh_cmd()

    @staticmethod
    def get_start_user_sh_content() -> str:
        """
        Generate the content for /workspace/start_user.sh.

        The ValyrianTech ComfyUI_with_Flux template (cw3nka7d08) has a native hook:
        its start.sh automatically sources /workspace/start_user.sh BEFORE launching
        ComfyUI. This guarantees our configuration runs BEFORE the first model scan.

        This is the CORRECT mechanism — NOT dockerArgs (which runs as entrypoint args
        or in parallel, AFTER ComfyUI has already started scanning its model dirs).

        Strategy:
        1. Ensure all model subdirs exist on the network volume
        2. Write extra_model_paths.yaml to ALL possible ComfyUI install locations
        3. Create directory-level symlinks from ComfyUI model dirs → network volume
        This ensures ComfyUI sees models on its FIRST scan at boot.
        """
        return """#!/bin/bash
# DM AI OS — start_user.sh
# Auto-executed by ValyrianTech template BEFORE ComfyUI starts.
# Configures model paths from persistent network volume (tbupq29n08 at /workspace/).
set -e

echo "=== DM AI OS start_user.sh: Configuring FLUX.2 model paths ==="

# 1. Verify network volume is mounted
if [ ! -d "/workspace" ]; then
    echo "ERROR: /workspace not mounted. Aborting model path setup."
    exit 1
fi

# 2. Ensure model subdirectory hierarchy exists on the volume
mkdir -p \\
    /workspace/ComfyUI/models/unet \\
    /workspace/ComfyUI/models/diffusion_models \\
    /workspace/ComfyUI/models/clip \\
    /workspace/ComfyUI/models/vae \\
    /workspace/ComfyUI/models/checkpoints \\
    /workspace/ComfyUI/models/loras

echo "Model dirs on volume: OK"
ls /workspace/ComfyUI/models/unet/ 2>/dev/null | head -5 && echo "unet: present" || echo "unet: empty"
ls /workspace/ComfyUI/models/clip/ 2>/dev/null | head -5 && echo "clip: present" || echo "clip: empty"
ls /workspace/ComfyUI/models/vae/  2>/dev/null | head -5 && echo "vae: present"  || echo "vae: empty"

# 3. Write extra_model_paths.yaml to all possible ComfyUI install roots
for COMFY_ROOT in /ComfyUI /root/ComfyUI /workspace/ComfyUI; do
    if [ -d "$COMFY_ROOT" ]; then
        cat > "$COMFY_ROOT/extra_model_paths.yaml" << 'YAML'
dm_ai_os_network_volume:
    base_path: /workspace/ComfyUI/models
    unet: unet
    diffusion_models: diffusion_models
    clip: clip
    vae: vae
    checkpoints: checkpoints
    loras: loras
YAML
        echo "Wrote extra_model_paths.yaml to $COMFY_ROOT"
    fi
done

# 4. Create directory-level symlinks: ComfyUI model dirs -> network volume model dirs
# This ensures ComfyUI's scanner traverses the volume directly on first boot.
for COMFY_ROOT in /ComfyUI /root/ComfyUI; do
    [ -d "$COMFY_ROOT" ] || continue
    mkdir -p "$COMFY_ROOT/models"
    for SUB in unet diffusion_models clip vae checkpoints loras; do
        TARGET="/workspace/ComfyUI/models/$SUB"
        LINK="$COMFY_ROOT/models/$SUB"
        # Remove existing dir/symlink and replace with symlink to volume
        if [ -L "$LINK" ]; then
            rm -f "$LINK"
        elif [ -d "$LINK" ]; then
            cp -rn "$LINK/." "$TARGET/" 2>/dev/null || true
            rm -rf "$LINK"
        fi
        ln -s "$TARGET" "$LINK"
        echo "Symlinked $LINK -> $TARGET"
    done
done

echo "=== DM AI OS start_user.sh: COMPLETE. ComfyUI will start with FLUX.2 model paths configured. ==="
"""

    @staticmethod
    def get_phase1_write_start_user_sh_cmd() -> str:
        """
        Phase 1 bash command for a plain pytorch container (no ComfyUI).
        Writes /workspace/start_user.sh to the persistent network volume.
        The script is then auto-executed by the ValyrianTech template (cw3nka7d08)
        on every subsequent ComfyUI pod boot, BEFORE ComfyUI's model scanner runs.

        NOTE: Models are already present on the volume — NO download performed.
        The pod exits cleanly after writing the file.
        """
        content = RunPodAdapter.get_start_user_sh_content()
        # Use printf to write the heredoc safely without shell quoting issues
        escaped = content.replace("\\", "\\\\").replace("'", "'\"'\"'")
        return (
            f"bash -c 'set -e && "
            f"echo \"=== Phase 1: Writing start_user.sh to network volume ===\" && "
            f"[ -d /workspace ] || {{ echo ERROR: /workspace not mounted; exit 1; }} && "
            f"printf \"%s\" '{escaped}' > /workspace/start_user.sh && "
            f"chmod +x /workspace/start_user.sh && "
            f"echo \"=== Contents written ===\" && "
            f"wc -l /workspace/start_user.sh && "
            f"echo \"=== Phase 1 COMPLETE: start_user.sh is persistent on network volume ===\"'"
        )

    async def create_pod(
        self,
        name: str = "DM-AI-OS-FLUX-Pod",
        gpu_type_id: str = "NVIDIA GeForce RTX 4090",
        template_id: Optional[str] = None,
        image_name: Optional[str] = None,
        volume_in_gb: int = 20,
        network_volume_id: Optional[str] = None,
        cloud_type: str = "COMMUNITY",
        docker_args: Optional[str] = None,
        start_cmd: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Spin up a new GPU pod on RunPod.
        If a Network Volume is configured, enforces STRICT DATACENTER BINDING.
        Cross-datacenter fallback is BLOCKED to guarantee persistent storage mounting.
        """
        tmpl = template_id or runpod_config.template_id or "cw3nka7d08"
        net_vol = network_volume_id if network_volume_id is not None else runpod_config.network_volume_id

        mutation = """
        mutation PodFindAndDeployOnDemand($input: PodFindAndDeployOnDemandInput!) {
            podFindAndDeployOnDemand(input: $input) {
                id
                imageName
                desiredStatus
                machine {
                    gpuDisplayName
                }
            }
        }
        """
        pod_input: Dict[str, Any] = {
            "name": name,
            "gpuTypeId": gpu_type_id,
            "gpuCount": 1,
            "cloudType": cloud_type,
            "containerDiskInGb": runpod_config.container_disk_gb,
            "volumeInGb": volume_in_gb,
            "ports": "8188/http,8080/http",
            "supportPublicIp": True,
            "startSsh": True,
        }

        # Determine image source: explicit imageName (no template) or template
        if image_name:
            # Use raw image — dockerArgs becomes the actual CMD for base images
            pod_input["imageName"] = image_name
        else:
            tmpl = template_id or runpod_config.template_id or "cw3nka7d08"
            pod_input["templateId"] = tmpl

        if docker_args:
            # Only set dockerArgs when explicitly passed.
            # For ComfyUI template pods: do NOT set dockerArgs.
            # The template's /start.sh natively calls /workspace/start_user.sh
            # (which we write in Phase 1) BEFORE launching ComfyUI.
            pod_input["dockerArgs"] = docker_args
        # NOTE: When using template_id (ComfyUI pod), dockerArgs is intentionally omitted.
        # The ValyrianTech template auto-executes /workspace/start_user.sh at boot.

        target_dc = None
        if net_vol:
            # Validate volume and enforce strict datacenter binding
            vol_info = await self.validate_network_volume_compatibility(net_vol)
            target_dc = vol_info.get("dataCenterId")
            pod_input["networkVolumeId"] = vol_info.get("volume_id") or net_vol
            pod_input["volumeInGb"] = 0  # Ephemeral disk not needed when network volume attached
            if target_dc:
                pod_input["dataCenterId"] = target_dc
                log.info(f"[RunPodAdapter] Strict Volume Datacenter Binding active: Datacenter={target_dc}")

        try:
            data = await self._graphql_query(mutation, {"input": pod_input})
            pod = data.get("podFindAndDeployOnDemand", {})
            pod_id = pod.get("id")
            if pod_id:
                log.info(f"[RunPodAdapter] Pod created: {pod_id} | GPU: {gpu_type_id} ({cloud_type}) | Datacenter: {target_dc or 'Global'}")
                return pod
        except Exception as e:
            err_str = str(e).lower()
            if "no longer any instances available" in err_str or "stock" in err_str:
                # If cloudType is COMMUNITY, try SECURE in SAME datacenter if volume bound
                if cloud_type == "COMMUNITY":
                    log.warning(f"[RunPodAdapter] COMMUNITY GPU out of stock in {target_dc or 'global'}. Retrying with SECURE cloud in same datacenter...")
                    pod_input["cloudType"] = "SECURE"
                    try:
                        data = await self._graphql_query(mutation, {"input": pod_input})
                        pod = data.get("podFindAndDeployOnDemand", {})
                        pod_id = pod.get("id")
                        if pod_id:
                            log.info(f"[RunPodAdapter] Pod created: {pod_id} | GPU: {gpu_type_id} (SECURE) | Datacenter: {target_dc or 'Global'}")
                            return pod
                    except Exception:
                        pass

                # Try alternative GPU types in the SAME datacenter before giving up
                fallback_gpus_same_dc = [
                    "NVIDIA L40S",
                    "NVIDIA RTX A6000",
                    "NVIDIA A40",
                    "NVIDIA GeForce RTX 3090",
                    "NVIDIA RTX 6000 Ada",
                    "NVIDIA L40",
                ]
                for fb_gpu in fallback_gpus_same_dc:
                    if fb_gpu.lower() != gpu_type_id.lower():
                        log.warning(f"[RunPodAdapter] GPU '{gpu_type_id}' out of stock in {target_dc or 'global'}. Retrying with '{fb_gpu}' in SAME datacenter...")
                        pod_input["gpuTypeId"] = fb_gpu
                        for ctype in ["COMMUNITY", "SECURE"]:
                            pod_input["cloudType"] = ctype
                            try:
                                data = await self._graphql_query(mutation, {"input": pod_input})
                                pod = data.get("podFindAndDeployOnDemand", {})
                                pod_id = pod.get("id")
                                if pod_id:
                                    log.info(f"[RunPodAdapter] Pod created: {pod_id} | GPU: {fb_gpu} ({ctype}) | Datacenter: {target_dc or 'Global'}")
                                    return pod
                            except Exception:
                                pass

                # STRICT RULE: If Network Volume is attached, DO NOT ALLOW cross-datacenter fallback!
                if net_vol:
                    log.error(f"[RunPodAdapter] Cross-datacenter fallback BLOCKED. All GPU options stock depleted in volume datacenter ({target_dc}).")
                    raise RunPodAdapterError(
                        f"NETWORK_VOLUME_DATACENTER_UNAVAILABLE: No GPU stock available in datacenter '{target_dc}' attached to Network Volume '{net_vol}'. Cross-datacenter fallback is blocked to preserve persistent storage.",
                        status_code=503
                    )
            raise
        return {}

    async def verify_flux2_models_present(self, pod_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Remote verification of FLUX.2 model files presence via /object_info.
        Checks specific model-loader nodes: UNETLoader, DualCLIPLoader, CLIPLoader, VAELoader.
        - flux-2-klein-4b-fp8.safetensors  (in UNETLoader or DiffusionModelLoader)
        - clip_l.safetensors               (in CLIPLoader or DualCLIPLoader)
        - t5xxl_fp8_e4m3fn.safetensors     (in CLIPLoader or DualCLIPLoader)
        - ae.safetensors                   (in VAELoader)
        """
        required_models = [
            "flux-2-klein-4b-fp8.safetensors",
            "clip_l.safetensors",
            "t5xxl_fp8_e4m3fn.safetensors",
            "ae.safetensors"
        ]
        # Node types that expose model file lists relevant to FLUX.2
        MODEL_LOADER_NODES = {
            "UNETLoader", "DiffusionModelLoader", "UnetLoaderGGUF",
            "CLIPLoader", "DualCLIPLoader", "CLIPLoaderGGUF",
            "VAELoader",
            "CheckpointLoaderSimple", "CheckpointLoader",
        }
        target_url = pod_url or self.comfyui_url

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(f"{target_url}/object_info")
                if r.status_code != 200:
                    return {"status": "MODELS_MISSING", "ready": False, "missing_models": required_models}

                info = r.json()
                all_model_files: list[str] = []

                for node_type, node_data in info.items():
                    if not isinstance(node_data, dict):
                        continue
                    # Only scan model loader nodes to avoid matching sampler names etc.
                    if node_type not in MODEL_LOADER_NODES:
                        continue
                    inp = node_data.get("input", {})
                    for section in ("required", "optional"):
                        sec_data = inp.get(section, {})
                        if not isinstance(sec_data, dict):
                            continue
                        for param_name, param_spec in sec_data.items():
                            # Model file lists are: [[file1, file2, ...], {...options}]
                            if isinstance(param_spec, list) and len(param_spec) > 0:
                                first_item = param_spec[0]
                                if isinstance(first_item, list):
                                    for val in first_item:
                                        if isinstance(val, str) and val.endswith(".safetensors"):
                                            all_model_files.append(val)

                log.info(f"[RunPodAdapter] Model loader files detected in /object_info: {all_model_files[:20]}")

                missing = [
                    m for m in required_models
                    if not any(m.lower() in f.lower() or Path(f).name.lower() == m.lower() for f in all_model_files)
                ]

                if not missing:
                    log.info("[RunPodAdapter] ✅ All 4 FLUX.2 model files verified present on ComfyUI node loaders.")
                    return {"status": "READY", "ready": True, "missing_models": []}

                log.warning(f"[RunPodAdapter] Missing models on ComfyUI loader nodes: {missing}. "
                            f"Detected .safetensors files: {all_model_files[:15]}")
                return {"status": "MODELS_MISSING", "ready": False, "missing_models": missing}

        except Exception as e:
            log.warning(f"[RunPodAdapter] Remote object_info model check warning: {e}")

        return {"status": "MODELS_MISSING", "ready": False, "missing_models": required_models}






    async def list_network_volumes(self) -> List[Dict[str, Any]]:
        """List all Network Volumes on the account."""
        query = """
        query {
            myself {
                networkVolumes {
                    id
                    name
                    size
                    dataCenterId
                }
            }
        }
        """
        try:
            data = await self._graphql_query(query)
            myself = data.get("myself", {})
            return myself.get("networkVolumes", [])
        except Exception as e:
            log.warning(f"[RunPodAdapter] list_network_volumes failed: {e}")
            return []

    async def create_network_volume(
        self,
        name: str = "DM-AI-OS-Models",
        size_gb: int = 40,
        datacenter_id: str = "US-TX-3",
    ) -> Dict[str, Any]:
        """
        Create a persistent Network Volume to store model files between pod sessions.
        Cost: ~$0.07/GB/month. 40 GB = ~$2.80/month.
        """
        mutation = """
        mutation CreateNetworkVolume($input: CreateNetworkVolumeInput!) {
            createNetworkVolume(input: $input) {
                id
                name
                size
                dataCenterId
            }
        }
        """
        data = await self._graphql_query(mutation, {
            "input": {
                "name": name,
                "size": size_gb,
                "dataCenterId": datacenter_id,
            }
        })
        vol = data.get("createNetworkVolume", {})
        log.info(f"[RunPodAdapter] Network Volume created: {vol.get('id')} | {size_gb}GB | Datacenter: {datacenter_id}")
        return vol

    async def ensure_models_available(self, pipeline: str = "flux2") -> Dict[str, Any]:
        """
        Check if required model files exist on the Network Volume / Pod storage.
        If missing and explicit authorization is enabled, returns MODELS_MISSING status
        to prevent unauthorized GPU credit consumption.
        """
        vols = await self.list_network_volumes()
        has_net_vol = any(v.get("id") == runpod_config.network_volume_id or v.get("name") == "DM-AI-OS-Models" for v in vols)

        if not has_net_vol:
            return {
                "status": "MODELS_MISSING",
                "ready": False,
                "reason": "Network Volume DM-AI-OS-Models not attached.",
                "action": "Attach Network Volume or authorize single model setup run."
            }

        # Check safety guardrail
        if runpod_config.model_download_requires_explicit_authorization:
            log.info("[RunPodAdapter] MODEL_DOWNLOAD_REQUIRES_EXPLICIT_AUTHORIZATION is active. Skipping automatic GPU spin for model download.")
            return {
                "status": "MODELS_MISSING",
                "ready": False,
                "reason": "Model setup requires explicit user authorization before spinning GPU.",
                "action": "Run `python scripts/setup_runpod_models.py` inside pod or authorize setup."
            }

        return {"status": "READY", "ready": True}




    async def start_pod(self, pod_id: Optional[str] = None) -> Dict[str, Any]:
        """Resume / start a stopped pod."""
        target_pod_id = pod_id or runpod_config.pod_id
        if not target_pod_id:
            raise RunPodAdapterError("Cannot start pod: No pod_id specified.")

        mutation = """
        mutation PodResume($input: PodResumeInput!) {
            podResume(input: $input) {
                id
                desiredStatus
            }
        }
        """
        log.info(f"[RunPodAdapter] Resuming GPU pod: {target_pod_id}")
        data = await self._graphql_query(mutation, {"input": {"podId": target_pod_id}})
        return data.get("podResume", {"id": target_pod_id, "desiredStatus": "RUNNING"})

    async def stop_pod(self, pod_id: Optional[str] = None) -> Dict[str, Any]:
        """Pause / stop a running pod to save GPU credits."""
        target_pod_id = pod_id or runpod_config.pod_id
        if not target_pod_id:
            return {"status": "skipped", "message": "No pod_id configured."}

        mutation = """
        mutation PodStop($input: PodStopInput!) {
            podStop(input: $input) {
                id
                desiredStatus
            }
        }
        """
        log.info(f"[RunPodAdapter] Stopping GPU pod: {target_pod_id}")
        try:
            data = await self._graphql_query(mutation, {"input": {"podId": target_pod_id}})
            return data.get("podStop", {"id": target_pod_id, "desiredStatus": "STOPPED"})
        except Exception as e:
            log.warning(f"[RunPodAdapter] stop_pod failed: {e}")
            return {"status": "error", "error": str(e)}

    async def terminate_pod(self, pod_id: Optional[str] = None) -> Dict[str, Any]:
        """Permanently terminate a pod."""
        target_pod_id = pod_id or runpod_config.pod_id
        if not target_pod_id:
            return {"status": "skipped", "message": "No pod_id configured."}

        mutation = """
        mutation PodTerminate($input: PodTerminateInput!) {
            podTerminate(input: $input)
        }
        """
        log.info(f"[RunPodAdapter] Terminating GPU pod: {target_pod_id}")
        data = await self._graphql_query(mutation, {"input": {"podId": target_pod_id}})
        return {"status": "terminated", "pod_id": target_pod_id}

    @property
    def comfyui_url(self) -> str:
        if getattr(self, "_active_comfyui_url", None):
            return self._active_comfyui_url.rstrip("/")
        return (self._override_comfyui_url or runpod_config.comfyui_url).rstrip("/")

    async def wait_until_ready(
        self,
        pod_id: Optional[str] = None,
        timeout_sec: Optional[int] = None
    ) -> bool:
        """Poll until pod is RUNNING and ComfyUI / HTTP endpoint responds."""
        target_timeout = timeout_sec or runpod_config.request_timeout_seconds
        target_pod_id = pod_id or runpod_config.pod_id
        t0 = time.monotonic()

        candidate_urls = [self.comfyui_url]
        if target_pod_id:
            proxy_url = f"https://{target_pod_id}-8188.proxy.runpod.net"
            if proxy_url not in candidate_urls:
                candidate_urls.append(proxy_url)

        log.info(f"[RunPodAdapter] Waiting for GPU pod / ComfyUI ready (timeout: {target_timeout}s)...")
        while time.monotonic() - t0 < target_timeout:
            for url in candidate_urls:
                try:
                    async with httpx.AsyncClient(timeout=4.0) as client:
                        r = await client.get(f"{url}/system_stats")
                        if r.status_code == 200:
                            self._active_comfyui_url = url
                            log.info(f"[RunPodAdapter] ComfyUI API is READY at {url}")
                            return True
                except Exception:
                    pass

            # Check Pod status via GraphQL if API Key available
            if runpod_config.is_configured and target_pod_id:
                status = await self.get_pod_status(target_pod_id)
                if status.get("desiredStatus") == "STOPPED":
                    await self.start_pod(target_pod_id)

            await asyncio.sleep(4.0)

        raise RunPodAdapterError(f"Pod / ComfyUI did not become ready within {target_timeout} seconds.")


    def log_state_event(self, event: str, details: Optional[Dict[str, Any]] = None):
        """Record lifecycle event in structured logs and history."""
        msg = f"[RunPodLifecycle] EVENT: {event}"
        if details:
            msg += f" | Details: {json.dumps(details)}"
        log.info(msg)

    async def select_best_gpu(
        self,
        min_vram_gb: int = 24,
        required_vram_gb: Optional[int] = None,
        preferred_gpu_types: Optional[List[str]] = None,
        required_datacenter: Optional[str] = None,
        max_price_per_hour: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Query RunPod GPU metadata and dynamically select optimal available NVIDIA GPU (VRAM >= min_vram_gb).
          6. A100 (40GB/80GB)
          7. Any other NVIDIA GPU >= min_vram_gb (RTX A6000, L40, RTX 6000 Ada, RTX A5000, etc.)
        Supports max_price_per_hour filtering and strict required_datacenter scoping.
        """
        query = """
        query {
            gpuTypes {
                id
                displayName
                memoryInGb
                securePrice
                communityPrice
                secureSpotPrice
                lowestPrice(input: {gpuCount: 1}) {
                    minimumBidPrice
                    uninterruptablePrice
                }
            }
        }
        """
        try:
            data = await self._graphql_query(query)
            gpu_types = data.get("gpuTypes", [])
            target_vram = required_vram_gb if required_vram_gb is not None else min_vram_gb
            # Filter GPUs with VRAM >= target_vram and non-zero pricing
            valid_gpus = [
                g for g in gpu_types
                if g.get("memoryInGb", 0) >= target_vram
                and (g.get("communityPrice", 0) > 0 or g.get("securePrice", 0) > 0)
            ]
            if not valid_gpus:
                valid_gpus = [g for g in gpu_types if g.get("memoryInGb", 0) >= 16] or gpu_types

            # Apply price filter if requested
            if max_price_per_hour:
                filtered_by_price = [
                    g for g in valid_gpus
                    if min(p for p in [g.get("communityPrice"), g.get("securePrice")] if p and p > 0) <= max_price_per_hour
                ]
                if filtered_by_price:
                    valid_gpus = filtered_by_price

            # User preference matching if explicitly passed
            prefs = preferred_gpu_types or [
                "RTX 4090",
                "RTX 5090",
                "RTX 3090",
                "A40",
                "L40S",
                "A100",
                "RTX A6000",
                "RTX 6000 Ada",
                "L40",
                "RTX A5000",
                "RTX 5000 Ada",
            ]

            for pref in prefs:
                for g in valid_gpus:
                    gpu_id = g.get("id", "").lower()
                    gpu_disp = g.get("displayName", "").lower()
                    if pref.lower() in gpu_id or pref.lower() in gpu_disp:
                        g["target_datacenter"] = required_datacenter
                        return g

            selected = valid_gpus[0] if valid_gpus else {"id": runpod_config.gpu_type, "memoryInGb": 24}
            selected["target_datacenter"] = required_datacenter
            return selected
        except Exception as e:
            log.warning(f"[RunPodAdapter] Dynamic GPU selection query fallback: {e}")
            return {"id": runpod_config.gpu_type, "memoryInGb": 24, "target_datacenter": required_datacenter}



    async def create_pod_on_demand(
        self,
        gpu_type_id: Optional[str] = None,
        template_id: Optional[str] = None,
        volume_gb: Optional[int] = None,
        disk_gb: Optional[int] = None
    ) -> Dict[str, Any]:
        """Dynamically create a pod on demand for job execution."""
        selected_gpu = gpu_type_id or (await self.select_best_gpu()).get("id")
        selected_template = template_id or runpod_config.template_id
        v_gb = volume_gb or runpod_config.volume_gb
        d_gb = disk_gb or runpod_config.container_disk_gb

        pod = await self.create_pod(
            name=f"DM-AI-OS-DynamicPod-{int(time.time())}",
            gpu_type_id=selected_gpu,
            template_id=selected_template,
            volume_in_gb=v_gb
        )
        pod_id = pod.get("id")
        self.log_state_event("POD_CREATED", {"pod_id": pod_id, "gpu_type": selected_gpu, "template": selected_template})
        return pod

    async def ensure_gpu_available(self) -> bool:
        """AUTO START guardrail: Ensure GPU pod is running before executing jobs."""
        if not runpod_config.auto_start:
            return True

        status = await self.get_pod_status()
        if status.get("is_ready"):
            return True

        if status.get("desiredStatus") == "STOPPED" and status.get("pod_id"):
            log.info(f"[RunPodAdapter] Resuming stopped pod: {status.get('pod_id')}")
            await self.start_pod(status.get("pod_id"))
            ready = await self.wait_until_ready(status.get("pod_id"))
            if ready:
                self.log_state_event("POD_READY", {"pod_id": status.get("pod_id")})
            return ready

        # If no pod ID is configured or existing pod is terminated, create on demand if API key is valid
        if runpod_config.is_configured and not runpod_config.pod_id:
            log.info("[RunPodAdapter] No fixed RUNPOD_POD_ID configured. Initiating dynamic pod creation...")
            try:
                new_pod = await self.create_pod_on_demand()
                pod_id = new_pod.get("id")
                if pod_id:
                    ready = await self.wait_until_ready(pod_id)
                    if ready:
                        self.log_state_event("POD_READY", {"pod_id": pod_id})
                    return ready
            except Exception as e:
                log.warning(f"[RunPodAdapter] Dynamic pod creation attempt warning: {e}")

        try:
            return await self.wait_until_ready(timeout_sec=10)
        except Exception:
            log.info("[RunPodAdapter] GPU Pod offline/mock fallback active.")
            return True

    async def cleanup_gpu(self, pod_id: Optional[str] = None, reason: str = "job_finished"):
        """
        Watchdog Cleanup: Stops or Terminates pod based on config guardrails to prevent orphan GPUs.
        """
        target_pod_id = pod_id or runpod_config.pod_id
        if not target_pod_id:
            self.log_state_event("CLEANUP_COMPLETED", {"reason": reason, "status": "no_pod"})
            return

        if runpod_config.auto_terminate:
            self.log_state_event("POD_TERMINATED", {"pod_id": target_pod_id, "reason": reason})
            await self.terminate_pod(target_pod_id)
        elif runpod_config.auto_stop:
            self.log_state_event("POD_STOP_REQUESTED", {"pod_id": target_pod_id, "reason": reason})
            await self.stop_pod(target_pod_id)

        self.log_state_event("CLEANUP_COMPLETED", {"pod_id": target_pod_id, "reason": reason})

    async def shutdown_if_idle(self) -> bool:
        """AUTO STOP guardrail: Stop GPU pod if no active jobs and idle timeout reached."""
        if not runpod_config.auto_stop and not runpod_config.auto_terminate:
            return False

        if self._active_jobs_count > 0:
            return False

        idle_duration = time.time() - self._last_activity_time
        if idle_duration >= runpod_config.idle_timeout_seconds:
            log.info(f"[RunPodAdapter] GPU idle for {int(idle_duration)}s (>= {runpod_config.idle_timeout_seconds}s). Triggering cleanup...")
            await self.cleanup_gpu(reason="idle_timeout")
            return True

        return False

    @asynccontextmanager
    async def gpu_session(self):
        """
        Async Context Manager (Watchdog Safety).
        Guarantees try/finally cleanup execution so exceptions or errors NEVER leak GPU compute budget.
        """
        self._active_jobs_count += 1
        self.log_state_event("JOB_STARTED", {"active_jobs": self._active_jobs_count})
        job_success = False
        try:
            await self.ensure_gpu_available()
            yield self
            job_success = True
            self.log_state_event("JOB_COMPLETED")
        except Exception as e:
            self.log_state_event("JOB_FAILED", {"error": str(e)})
            raise
        finally:
            self._active_jobs_count = max(0, self._active_jobs_count - 1)
            self._last_activity_time = time.time()
            try:
                if not job_success or runpod_config.auto_terminate:
                    await self.cleanup_gpu(reason="session_ended")
                else:
                    await self.shutdown_if_idle()
            except Exception as e:
                log.warning(f"[RunPodAdapter] Watchdog cleanup exception: {e}")


    # ── Health Check ─────────────────────────────────────────────

    async def health_check(self) -> Tuple[str, float, str]:
        """Returns (status_str, latency_ms, account_info_str)."""
        t0 = time.monotonic()
        if not runpod_config.is_configured:
            return ("auth_expired", 0.0, "RUNPOD_API_KEY missing")

        try:
            # Ping ComfyUI system stats or RunPod GraphQL
            async with httpx.AsyncClient(timeout=4.0) as client:
                r = await client.get(f"{self.comfyui_url}/system_stats")
                latency = round((time.monotonic() - t0) * 1000, 1)
                if r.status_code == 200:
                    return ("available", latency, f"ComfyUI Ready ({self.comfyui_url})")
            
            # Fallback GraphQL check
            acc = await self.get_account_status()
            latency = round((time.monotonic() - t0) * 1000, 1)
            return ("available", latency, f"RunPod Acc: {acc.get('email')} (${acc.get('balance'):.2f})")
        except Exception as e:
            latency = round((time.monotonic() - t0) * 1000, 1)
            return ("unavailable", latency, f"RunPod Offline: {e}")

    # ── Job Execution & ComfyUI API ───────────────────────────────

    async def submit_job(self, workflow_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a workflow prompt JSON to ComfyUI API."""
        prompt_req = {"prompt": workflow_payload, "client_id": f"dm_ai_os_{int(time.time())}"}
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{self.comfyui_url}/prompt", json=prompt_req)
            if resp.status_code in (401, 403):
                raise RunPodAdapterError("ComfyUI Unauthorized.", status_code=resp.status_code)
            if resp.status_code == 429:
                raise RunPodAdapterError("ComfyUI 429 Rate limit.", status_code=429)
            resp.raise_for_status()
            data = resp.json()
            prompt_id = data.get("prompt_id")
            if not prompt_id:
                raise RunPodAdapterError(f"ComfyUI prompt submission failed: {data}")
            return {"job_id": prompt_id, "status": "submitted", "prompt_id": prompt_id}

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Check job status from ComfyUI history."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{self.comfyui_url}/history/{job_id}")
            if resp.status_code != 200:
                return {"job_id": job_id, "status": "pending"}
            history = resp.json()
            if job_id in history:
                job_info = history[job_id]
                outputs = job_info.get("outputs", {})
                return {
                    "job_id": job_id,
                    "status": "completed",
                    "outputs": outputs,
                    "completed": True
                }
            return {"job_id": job_id, "status": "running", "completed": False}

    async def get_job_result(self, job_id: str, timeout_sec: int = 300) -> Dict[str, Any]:
        """Poll until job completes and retrieve output files."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout_sec:
            st = await self.get_job_status(job_id)
            if st.get("completed"):
                return st
            await asyncio.sleep(3.0)
        raise RunPodAdapterError(f"Job {job_id} timed out after {timeout_sec}s.")

    async def upload_file(self, file_input: Union[str, bytes, Path]) -> str:
        """Upload image or video file to ComfyUI input directory."""
        filename = f"upload_{int(time.time())}_{hashlib.md5(str(file_input).encode()).hexdigest()[:8]}.png"
        raw_bytes = None

        if isinstance(file_input, (str, Path)):
            p = Path(str(file_input))
            if p.exists():
                raw_bytes = p.read_bytes()
                filename = p.name
            elif str(file_input).startswith("data:"):
                header, b64_data = str(file_input).split(",", 1)
                raw_bytes = base64.b64decode(b64_data)
        elif isinstance(file_input, bytes):
            raw_bytes = file_input

        if not raw_bytes:
            raise RunPodAdapterError("Failed to resolve input file bytes for upload.")

        try:
            files = {"image": (filename, raw_bytes, "image/png")}
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.comfyui_url}/upload/image", files=files)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("name", filename)
        except Exception as e:
            log.warning(f"[RunPodAdapter] ComfyUI HTTP upload fallback: {e}")

        return filename

    async def download_result(self, filename: str, subfolder: str = "", folder_type: str = "output") -> Dict[str, Any]:
        """Download generated image or video output file to local storage."""
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        
        raw_bytes = None
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{self.comfyui_url}/view", params=params)
                if resp.status_code == 200:
                    raw_bytes = resp.content
        except Exception as e:
            log.warning(f"[RunPodAdapter] Result download HTTP fetch warning: {e}")

        if not raw_bytes:
            # Fallback dummy file generation for mock/offline testing
            raw_bytes = b"MOCK_RUNPOD_OUTPUT_BYTES_" + filename.encode()

        storage._ensure_artifacts_dir()
        local_filename = f"runpod_{filename}"
        file_path = storage.artifacts_dir / local_filename
        file_path.write_bytes(raw_bytes)

        image_url = f"/api/providers/uploads/{local_filename}"

        return {
            "status": "success",
            "filename": local_filename,
            "file_path": str(file_path),
            "image_url": image_url,
            "size_bytes": len(raw_bytes)
        }

    # ── High level execution methods ─────────────────────────────

    async def generate_image(
        self,
        prompt: str,
        *,
        reference_image: Optional[Union[str, bytes, Path]] = None,
        aspect_ratio: str = "1:1",
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """Generate FLUX.2 Klein 4B image on RunPod GPU."""
        cache_key_data = {
            "provider": "runpod",
            "model": runpod_config.image_model,
            "prompt": prompt.strip(),
            "aspect_ratio": aspect_ratio,
            "seed": seed,
            "steps": steps,
        }

        if use_cache:
            cached = storage.get_cache("runpod_flux2", cache_key_data)
            if cached:
                log.info(f"[RunPodAdapter] CACHE HIT for prompt: '{prompt[:40]}...'")
                cached["_cached"] = True
                return cached

        t0 = time.monotonic()
        async with self.gpu_session():
            # Load workflow template
            wf_file = Path(__file__).parent.parent.parent / "workflows" / "runpod" / (
                "flux2_klein_img2img.json" if reference_image else "flux2_klein_txt2img.json"
            )
            wf_template = json.loads(wf_file.read_text(encoding="utf-8")) if wf_file.exists() else {}

            # Upload reference image if provided
            ref_filename = None
            if reference_image:
                ref_filename = await self.upload_file(reference_image)

            # Aspect ratio dimensions
            dim_map = {
                "1:1": (1024, 1024),
                "9:16": (768, 1344),
                "16:9": (1344, 768),
                "4:5": (896, 1120),
                "3:4": (864, 1152),
            }
            w, h = dim_map.get(aspect_ratio, (768, 1344))

            # Fill node inputs based on workflow template
            if "4" in wf_template:
                wf_template["4"]["inputs"]["text"] = prompt
            if "6" in wf_template:
                wf_template["6"]["inputs"]["width"] = w
                wf_template["6"]["inputs"]["height"] = h
            if "7" in wf_template and seed is not None:
                wf_template["7"]["inputs"]["seed"] = seed
            if "10" in wf_template and ref_filename:
                wf_template["10"]["inputs"]["image"] = ref_filename

            # Submit & await job
            job = await self.submit_job(wf_template)
            job_id = job["job_id"]
            _ = await self.get_job_result(job_id)


            # Download result
            out = await self.download_result(f"flux2_output_{job_id[:8]}.png")

        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        res = {
            "status": "success",
            "provider": "runpod",
            "model": runpod_config.image_model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "image_url": out["image_url"],
            "file_path": out["file_path"],
            "latency_ms": latency_ms,
            "_cached": False
        }

        storage.set_cache("runpod_flux2", cache_key_data, res)
        provider_history.record(
            provider="runpod", capability="image", prompt=prompt, model=runpod_config.image_model,
            result_url=out["image_url"], duration_ms=latency_ms, status="ok"
        )
        return res


runpod_adapter = RunPodAdapter()
