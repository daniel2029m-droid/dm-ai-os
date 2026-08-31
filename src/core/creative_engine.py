"""
CreativeEngine — High-level creative workflow orchestrator for DM AI OS.
Workflow-First execution, metadata tracking, and reproducibility vault.
"""
import os
import json
import time
import hashlib
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass, asdict

from ..adapters.comfy_adapter import comfy_adapter
from ..storage.storage_layer import storage
from .dynamic_slot_injector import slot_injector, SlotInjectionError, DynamicSlotInjector
from .model_registry import model_registry, ModelValidationError

log = logging.getLogger("creative_engine")

@dataclass
class CreativeManifest:
    job_id: str
    timestamp: str
    workflow_name: str
    workflow_sha256: str
    backend: str
    parameters: Dict[str, Any]
    prompt: str
    negative_prompt: Optional[str]
    input_assets: List[str]
    output_assets: List[str]
    duration_sec: float
    status: str
    estimated_cost_usd: Optional[float]
    error_message: Optional[str] = None

@dataclass
class CreativeManifestV2:
    job_id: str
    workflow_name: str
    workflow_template_sha256: str
    workflow_effective_sha256: str
    backend_type: str
    provider: str
    prompt: str
    created_at: str
    parameters: Dict[str, Any]
    idempotency_key: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    model_checkpoint: Optional[str] = None
    negative_prompt: Optional[str] = None
    input_assets: List[str] = None
    output_assets: List[str] = None
    output_sha256: Optional[str] = None
    output_size_bytes: Optional[int] = None
    dispatch_duration_sec: float = 0.0
    gpu_execution_duration_sec: Optional[float] = None
    total_e2e_duration_sec: Optional[float] = None
    status: str = "SUBMITTED"
    attempt: int = 1
    max_retries: int = 3
    estimated_cost_usd: Optional[float] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.input_assets is None:
            self.input_assets = []
        if self.output_assets is None:
            self.output_assets = []

class CreativeEngine:
    def __init__(self, workflows_dir: Optional[str] = None):
        if not workflows_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            workflows_dir = os.path.join(base_dir, "workflows")
        self.workflows_dir = Path(workflows_dir)

    def list_templates(self) -> List[Dict[str, Any]]:
        """Scans workflows directory and lists all JSON reproducible templates."""
        templates = []
        if not self.workflows_dir.exists():
            return templates
        for p in self.workflows_dir.rglob("*.json"):
            try:
                content = p.read_text(encoding="utf-8")
                h = hashlib.sha256(content.encode("utf-8")).hexdigest()
                templates.append({
                    "name": p.stem,
                    "filename": p.name,
                    "relative_path": str(p.relative_to(self.workflows_dir.parent)),
                    "sha256": h,
                    "sha256_short": h[:12],
                    "size_bytes": p.stat().st_size
                })
            except Exception as e:
                log.warning(f"[CreativeEngine] Error reading template {p}: {e}")
                continue
        return templates

    def get_template(self, name_or_path: str) -> Optional[Dict[str, Any]]:
        """Finds and loads a workflow JSON template by name or path."""
        # Check direct path first
        target_path = Path(name_or_path)
        if not target_path.exists() and not target_path.is_absolute():
            target_path = self.workflows_dir / name_or_path
            if not target_path.exists() and not str(name_or_path).endswith(".json"):
                target_path = self.workflows_dir / f"{name_or_path}.json"

        # Search recursively if not found
        if not target_path.exists():
            for p in self.workflows_dir.rglob("*.json"):
                if p.stem.lower() == name_or_path.lower() or p.name.lower() == name_or_path.lower():
                    target_path = p
                    break

        if target_path.exists():
            try:
                raw = target_path.read_text(encoding="utf-8")
                return {
                    "path": str(target_path),
                    "name": target_path.stem,
                    "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    "workflow": json.loads(raw)
                }
            except Exception as e:
                log.error(f"[CreativeEngine] Error loading template {target_path}: {e}")
        return None

    async def run_workflow(
        self,
        template_name_or_path: str,
        prompt: str,
        parameters: Optional[Dict[str, Any]] = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """Workflow-First execution with complete reproducibility manifest."""
        start_time = time.time()
        template_info = self.get_template(template_name_or_path)

        if not template_info:
            return {
                "status": "FAILED",
                "error": f"Workflow template '{template_name_or_path}' not found."
            }

        workflow_data = template_info["workflow"]
        workflow_hash = template_info["sha256"]
        workflow_name = template_info["name"]

        params = parameters.copy() if parameters else {}
        if prompt:
            params["prompt"] = prompt
        if negative_prompt is not None:
            params["negative_prompt"] = negative_prompt
        if seed is not None:
            params["seed"] = seed

        # Dynamic Slot Injection & Validation
        try:
            inj_res = slot_injector.process(
                template_workflow=workflow_data,
                user_params=params,
                model=workflow_name
            )
            effective_workflow = inj_res["effective_workflow"]
            effective_params = inj_res["effective_params"]
            template_hash = inj_res["workflow_template_sha256"]
            effective_hash = inj_res["workflow_effective_sha256"]
            idempotency_key = inj_res["idempotency_key"]
        except SlotInjectionError as se:
            log.warning(f"[CreativeEngine] Slot injection error: {se}")
            return {
                "status": "FAILED",
                "error": str(se),
                "error_code": se.error_code
            }
        except Exception as e:
            log.error(f"[CreativeEngine] Unexpected slot injection error: {e}")
            effective_workflow = workflow_data
            effective_params = params
            template_hash = workflow_hash
            effective_hash = workflow_hash
            idempotency_key = None

        # Model Registry Pre-Dispatch Validation
        target_model = effective_params.get("model") or effective_params.get("MODEL")
        if target_model:
            try:
                vram = effective_params.get("vram_gb") or effective_params.get("available_vram_gb")
                gpu = effective_params.get("gpu_name")
                model_registry.validate_model(
                    model_name=target_model,
                    workflow_name=workflow_name,
                    available_vram_gb=vram,
                    gpu_name=gpu
                )
            except ModelValidationError as mve:
                log.warning(f"[CreativeEngine] Pre-dispatch model validation rejected: {mve}")
                return {
                    "status": "FAILED",
                    "error": str(mve),
                    "error_code": mve.error_code,
                    "details": mve.details
                }

        # Idempotency Check: if identical job was already completed, return existing result without duplicate GPU work
        if idempotency_key:
            existing_job = storage.job_store.get_job_by_idempotency_key(idempotency_key)
            if existing_job and existing_job.get("status") == "COMPLETED":
                existing_manifest = {}
                manifest_path = storage.artifacts_dir / f"creative_manifest_{existing_job['job_id']}.json"
                if manifest_path.exists():
                    try:
                        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                log.info(f"[CreativeEngine] Idempotent hit for key {idempotency_key[:12]}: reusing job {existing_job['job_id']}")
                return {
                    "status": "COMPLETED",
                    "job_id": existing_job["job_id"],
                    "manifest": existing_manifest,
                    "backend": existing_job.get("backend_type", "REMOTE_COMFYUI"),
                    "response": {"status": "COMPLETED", "job_id": existing_job["job_id"], "reused": True},
                    "workflow_template_sha256": template_hash,
                    "workflow_effective_sha256": effective_hash,
                    "idempotency_key": idempotency_key,
                    "reused": True
                }

        # Auto-upload any referenced input image assets to remote ComfyUI input folder
        for key in ["INPUT_IMAGE", "input_image", "INPUT_IMAGE_1", "input_image_1", "INPUT_IMAGE_2", "input_image_2", "IMAGE_URL", "reference_image_url"]:
            val = effective_params.get(key)
            if val and isinstance(val, str):
                local_candidates = [
                    Path("deployment") / "uploads" / val,
                    Path(val),
                    Path("deployment") / "uploads" / os.path.basename(val),
                ]
                for p in local_candidates:
                    if p.exists() and p.is_file():
                        try:
                            up_name = await comfy_adapter.upload_image(p, p.name)
                            if up_name:
                                log.info(f"[CreativeEngine] Synced input image {p.name} -> ComfyUI input/{up_name}")
                        except Exception as e:
                            log.warning(f"[CreativeEngine] Failed uploading input image {p}: {e}")
                        break

        # Submit via ComfyAdapter using the effective resolved workflow
        res = await comfy_adapter.submit_workflow(effective_workflow, parameters=effective_params)

        duration = round(time.time() - start_time, 3)

        job_id = res.get("job_id", f"cr_{int(time.time())}_{effective_hash[:8]}")
        status = res.get("status", "SUBMITTED")
        backend = res.get("backend", comfy_adapter.preferred_backend.upper())
        error_msg = res.get("error")
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Build Reproducibility Manifest (v1 compatible)
        manifest = CreativeManifest(
            job_id=job_id,
            timestamp=created_at,
            workflow_name=workflow_name,
            workflow_sha256=template_hash,
            backend=backend,
            parameters=effective_params,
            prompt=prompt,
            negative_prompt=negative_prompt,
            input_assets=[],
            output_assets=[],
            duration_sec=duration,
            status=status,
            estimated_cost_usd=None, # Explicit null/None without inventing costs
            error_message=error_msg
        )

        # Build & Persist in JobStore (v2)
        try:
            storage.job_store.create_job({
                "job_id": job_id,
                "idempotency_key": idempotency_key,
                "status": status,
                "workflow_name": workflow_name,
                "workflow_template_sha256": template_hash,
                "workflow_effective_sha256": effective_hash,
                "backend_type": "REMOTE_COMFYUI" if "RUNPOD" in backend or "COMFY" in backend else backend,
                "provider": "auto",
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "parameters": effective_params,
                "input_assets": [],
                "output_assets": [],
                "dispatch_duration_sec": duration,
                "estimated_cost_usd": None,
                "error_message": error_msg,
                "created_at": created_at
            })
        except Exception as e:
            log.warning(f"[CreativeEngine] Could not record job in JobStore: {e}")

        # Save manifest to artifacts vault
        try:
            manifest_json = json.dumps(asdict(manifest), indent=2, ensure_ascii=False)
            storage.save_artifact(f"creative_manifest_{job_id}.json", manifest_json)
        except Exception as e:
            log.warning(f"[CreativeEngine] Could not save manifest artifact: {e}")

        return {
            "status": status,
            "job_id": job_id,
            "manifest": asdict(manifest),
            "backend": backend,
            "response": res,
            "workflow_template_sha256": template_hash,
            "workflow_effective_sha256": effective_hash,
            "idempotency_key": idempotency_key
        }

    async def download_and_vault_artifact(self, job_id: str) -> Dict[str, Any]:
        """
        Auto-Vaulting pipeline:
        1. Consults /history/{job_id} to extract outputs.
        2. Downloads bytes securely via /view.
        3. Saves safely inside Project_State/Artifacts/media/<job_id>/ with path traversal prevention.
        4. Calculates SHA-256 and byte size.
        5. Updates JobStore and CreativeManifest in Vault to COMPLETED.
        """
        storage._ensure_artifacts_dir()
        outputs = await comfy_adapter.get_job_outputs(job_id)
        if not outputs:
            return {
                "status": "FAILED",
                "job_id": job_id,
                "error": "No output assets available for job or job not completed yet."
            }

        saved_assets = []
        primary_sha256 = None
        primary_size = None

        # Base directory for media artifacts
        media_base = (storage.artifacts_dir / "media" / job_id).resolve()
        media_base.mkdir(parents=True, exist_ok=True)

        for item in outputs:
            filename = item.get("filename")
            subfolder = item.get("subfolder", "")
            file_type = item.get("type", "output")

            if not filename:
                continue

            # Secure path resolution preventing path traversal
            safe_filename = Path(filename).name
            dest_file = (media_base / safe_filename).resolve()

            # Ensure dest_file is strictly inside media_base
            if not str(dest_file).startswith(str(media_base)):
                log.error(f"[CreativeEngine] Path traversal attempt detected for file: {filename}")
                continue

            content_bytes = await comfy_adapter.download_output_bytes(
                filename=safe_filename,
                subfolder=subfolder,
                file_type=file_type
            )

            if content_bytes is not None:
                # Write to temp file then atomic rename for crash safety
                temp_dest = dest_file.with_suffix(f"{dest_file.suffix}.tmp")
                temp_dest.write_bytes(content_bytes)
                temp_dest.replace(dest_file)

                file_sha256 = hashlib.sha256(content_bytes).hexdigest()
                file_size = len(content_bytes)

                rel_path = str(dest_file.relative_to(storage.artifacts_dir.parent))
                saved_assets.append(rel_path)

                if primary_sha256 is None:
                    primary_sha256 = file_sha256
                    primary_size = file_size

                log.info(f"[CreativeEngine] Successfully vaulted asset: {dest_file} ({file_size} bytes, sha256={file_sha256[:12]})")

        if not saved_assets:
            return {
                "status": "FAILED",
                "job_id": job_id,
                "error": "Failed to download output media from remote ComfyUI."
            }

        completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Update JobStore
        storage.job_store.update_job(job_id, {
            "status": "COMPLETED",
            "output_assets": saved_assets,
            "output_sha256": primary_sha256,
            "output_size_bytes": primary_size,
            "completed_at": completed_at
        })

        # Update Manifest in Artifacts Vault
        manifest_path = storage.artifacts_dir / f"creative_manifest_{job_id}.json"
        manifest_dict = {}
        if manifest_path.exists():
            try:
                manifest_dict = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        manifest_dict.update({
            "status": "COMPLETED",
            "output_assets": saved_assets,
            "output_sha256": primary_sha256,
            "output_size_bytes": primary_size,
            "completed_at": completed_at
        })
        # Export deliverable to accessible user library (C:\Users\moral\DM_AI_OS_OUTPUTS\)
        user_deliverables = []
        try:
            from ..storage.user_outputs import user_outputs
            for saved_rel in saved_assets:
                source_f = (storage.artifacts_dir.parent / saved_rel).resolve()
                success, dest_p, _ = user_outputs.export_asset(
                    vault_file=source_f,
                    job_id=job_id,
                    workflow_name=manifest_dict.get("workflow_name", "")
                )
                if success and dest_p:
                    user_deliverables.append(str(dest_p))
        except Exception as e:
            log.warning(f"[CreativeEngine] User outputs mirror error: {e}")

        # Also vault output into CloudAssetStorage (Google One 5 TB) if mounted
        try:
            from ..storage.cloud_asset_storage import cloud_asset_storage
            if cloud_asset_storage.is_mounted():
                for saved_rel in saved_assets:
                    source_f = (storage.artifacts_dir.parent / saved_rel).resolve()
                    cloud_asset_storage.vault_generated_output(source_f, job_id=job_id)
        except Exception as e:
            log.debug(f"[CreativeEngine] Cloud storage sync skipped/failed: {e}")

        return {
            "status": "COMPLETED",
            "job_id": job_id,
            "output_assets": saved_assets,
            "user_deliverables": user_deliverables,
            "output_sha256": primary_sha256,
            "output_size_bytes": primary_size,
            "completed_at": completed_at
        }


    # ── High-Level Intent Methods ──────────────────────────────────────────

    async def submit_generation_job(
        self,
        task_type: str,
        prompt: str = "",
        model_name: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        input_assets: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        High-level entrypoint for all creative generation jobs.
        1. Evaluates intent and hardware constraints via ModelRouter.
        2. If GPU worker is offline, returns REQUIRES_ACTIVATION with 1-click Colab URL.
        3. If GPU worker is READY, resolves optimal workflow from WorkflowRegistry and dispatches.
        """
        from .model_router import model_router, ExecutionTarget
        from .workflow_registry import workflow_registry, CreativeTask

        params = parameters.copy() if parameters else {}
        route = model_router.route_intent(task_type=task_type, prompt=prompt, model_name=model_name)

        if route.target == ExecutionTarget.REQUIRES_ACTIVATION:
            job_id = f"job_queued_{int(time.time())}"
            created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            try:
                storage.job_store.create_job({
                    "job_id": job_id,
                    "status": "REQUIRES_ACTIVATION",
                    "workflow_name": route.model_id,
                    "backend_type": "COLAB_T4_GPU",
                    "provider": "google-colab",
                    "prompt": prompt,
                    "parameters": params,
                    "error_message": route.reason,
                    "created_at": created_at
                })
            except Exception:
                pass

            return {
                "status": "REQUIRES_ACTIVATION",
                "job_id": job_id,
                "model_id": route.model_id,
                "target": route.target.value,
                "message": route.reason,
                "activation_url": route.activation_url,
                "instructions": "Pachu local hardware cannot execute heavy visual models. Click activation link to launch Google Colab Tesla T4 worker."
            }

        # Resolve workflow template
        has_ref = bool(input_assets and len(input_assets) > 0)
        task_enum = CreativeTask.IMAGE_TXT2IMG
        if "upscale" in task_type.lower():
            task_enum = CreativeTask.IMAGE_UPSCALE
        elif "video" in task_type.lower():
            task_enum = CreativeTask.VIDEO_TXT2VID if not has_ref else CreativeTask.VIDEO_I2V
        elif "tts" in task_type.lower():
            task_enum = CreativeTask.AUDIO_TTS
        elif "lipsync" in task_type.lower():
            task_enum = CreativeTask.VIDEO_LIPSYNC
        elif "img2img" in task_type.lower() or has_ref:
            task_enum = CreativeTask.IMAGE_IMG2IMG

        wf_info = workflow_registry.select_workflow(
            task=task_enum,
            preferred_model=route.model_id,
            has_reference_image=has_ref
        )
        template_name = wf_info.get("template", "zimage_turbo_txt2img")

        # Merge input assets into parameters if provided
        if input_assets:
            if "image" in task_type.lower() or "upscale" in task_type.lower() or "lipsync" in task_type.lower():
                params["INPUT_IMAGE"] = input_assets[0]
            if "lipsync" in task_type.lower() and len(input_assets) > 1:
                params["INPUT_AUDIO"] = input_assets[1]

        # Dispatch workflow
        return await self.run_workflow(
            template_name_or_path=template_name,
            prompt=prompt,
            parameters=params,
            negative_prompt=negative_prompt,
            seed=seed
        )

    async def generate(
        self,
        prompt: str,
        task: str = "image_generation",
        model: Optional[str] = None,
        width: int = 1024,
        height: int = 1024,
        steps: int = 20,
        cfg: float = 7.0,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Convenience method for image generation (Z-Image Turbo, FLUX.2, SD15)."""
        params = {
            "WIDTH": width,
            "HEIGHT": height,
            "STEPS": steps,
            "CFG": cfg,
            "DENOISE": kwargs.get("denoise", 1.0)
        }
        params.update(kwargs)
        return await self.submit_generation_job(
            task_type=task,
            prompt=prompt,
            model_name=model,
            parameters=params,
            negative_prompt=negative_prompt,
            seed=seed
        )

    async def video(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        model: Optional[str] = None,
        width: int = 768,
        height: int = 512,
        steps: int = 20,
        **kwargs
    ) -> Dict[str, Any]:
        """Convenience method for video generation (LTX-Video, Wan 2.2, MiniMax H3)."""
        params = {"WIDTH": width, "HEIGHT": height, "STEPS": steps}
        params.update(kwargs)
        inputs = [image_path] if image_path else []
        return await self.submit_generation_job(
            task_type="video_generation",
            prompt=prompt,
            model_name=model or "ltx_video",
            parameters=params,
            input_assets=inputs
        )

    async def upscale(
        self,
        image_path: str,
        model: Optional[str] = None,
        scale: int = 4,
        **kwargs
    ) -> Dict[str, Any]:
        """Convenience method for image super-resolution (SeedVR2)."""
        params = {"scale": scale}
        params.update(kwargs)
        return await self.submit_generation_job(
            task_type="image_upscale",
            prompt="",
            model_name=model or "seedvr2_upscale",
            parameters=params,
            input_assets=[image_path]
        )

    async def tts(
        self,
        text: str,
        model: Optional[str] = None,
        voice_reference: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Convenience method for text-to-speech audio synthesis (Qwen3-TTS)."""
        params = {"voice_reference": voice_reference}
        params.update(kwargs)
        return await self.submit_generation_job(
            task_type="audio_tts",
            prompt=text,
            model_name=model or "qwen3_tts",
            parameters=params
        )

    async def lipsync(
        self,
        image_or_video_path: str,
        audio_path: str,
        model: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Convenience method for audio/video lipsync synchronization (FLOAT)."""
        params = {}
        params.update(kwargs)
        return await self.submit_generation_job(
            task_type="video_lipsync",
            prompt="",
            model_name=model or "comfyui_float",
            parameters=params,
            input_assets=[image_or_video_path, audio_path]
        )


# Singleton instance
creative_engine = CreativeEngine()

