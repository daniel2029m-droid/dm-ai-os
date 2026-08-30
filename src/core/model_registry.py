"""
ModelRegistry — Declarative model, architecture, and GPU compatibility registry for DM AI OS v1.5.1.
Enforces pre-dispatch validation preventing resource waste and runtime failures.
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

log = logging.getLogger("model_registry")

class ModelValidationError(ValueError):
    """Raised when model validation fails prior to workflow dispatch."""
    def __init__(self, message: str, error_code: str = "MODEL_VALIDATION_FAILED", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


class ModelRegistry:
    """
    Manages declarative model definitions, VRAM requirements, GPU compatibility, and workflow binding.
    """

    def __init__(self, config_path: Optional[str] = None):
        if not config_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config_path = os.path.join(base_dir, "config", "model_registry.json")
        self.config_path = Path(config_path)
        self._registry_cache: Optional[Dict[str, Any]] = None

    def load_registry(self) -> Dict[str, Any]:
        """Loads and caches the model registry JSON configuration."""
        if not self.config_path.exists():
            log.warning(f"[ModelRegistry] Config file not found at {self.config_path}. Returning empty registry.")
            return {"models": {}}

        try:
            raw = self.config_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict) or "models" not in data:
                log.warning(f"[ModelRegistry] Invalid schema in {self.config_path}. 'models' key required.")
                return {"models": {}}
            self._registry_cache = data
            return data
        except Exception as e:
            log.error(f"[ModelRegistry] Error parsing {self.config_path}: {e}")
            return {"models": {}}

    def list_models(self) -> List[Dict[str, Any]]:
        """Returns all registered models with their metadata."""
        data = self.load_registry()
        models = []
        for name, meta in data.get("models", {}).items():
            entry = meta.copy()
            entry["model_id"] = name
            models.append(entry)
        return models

    def get_model(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Looks up model metadata by exact or lowercase name."""
        data = self.load_registry()
        models_map = data.get("models", {})
        if model_name in models_map:
            res = models_map[model_name].copy()
            res["model_id"] = model_name
            return res

        target = model_name.lower().strip()
        for k, v in models_map.items():
            if k.lower() == target or target in k.lower():
                res = v.copy()
                res["model_id"] = k
                return res
        return None

    def find_model_for_workflow(self, workflow_name: str) -> Optional[Dict[str, Any]]:
        """Finds the default registered model associated with a workflow template."""
        data = self.load_registry()
        wf_target = workflow_name.lower().replace(".json", "")
        for k, v in data.get("models", {}).items():
            compat_wfs = [w.lower() for w in v.get("compatible_workflows", [])]
            if wf_target in compat_wfs or k.lower() in wf_target:
                res = v.copy()
                res["model_id"] = k
                return res
        return None

    def validate_model(
        self,
        model_name: str,
        workflow_name: Optional[str] = None,
        available_vram_gb: Optional[float] = None,
        gpu_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validates model existence, workflow compatibility, VRAM constraints, and GPU compatibility.
        Raises ModelValidationError if invalid. Returns model info dict on success.
        """
        model_info = self.get_model(model_name)
        if not model_info:
            raise ModelValidationError(
                f"Model '{model_name}' is not registered in model_registry.json.",
                error_code="MODEL_NOT_REGISTERED",
                details={"model_name": model_name}
            )

        # 1. Workflow compatibility check
        if workflow_name:
            wf_clean = workflow_name.lower().replace(".json", "")
            compat_wfs = [w.lower() for w in model_info.get("compatible_workflows", [])]
            if compat_wfs and wf_clean not in compat_wfs and not any(wf_clean in cw for cw in compat_wfs):
                raise ModelValidationError(
                    f"Model '{model_name}' is incompatible with workflow '{workflow_name}'. Allowed: {compat_wfs}",
                    error_code="MODEL_WORKFLOW_INCOMPATIBLE",
                    details={"model_name": model_name, "workflow_name": workflow_name, "compatible_workflows": compat_wfs}
                )

        # 2. VRAM constraint check
        if available_vram_gb is not None:
            min_vram = model_info.get("min_vram_gb", 0.0)
            if available_vram_gb < min_vram:
                raise ModelValidationError(
                    f"Insufficient VRAM for model '{model_name}': requires minimum {min_vram} GB, available: {available_vram_gb:.1f} GB.",
                    error_code="INSUFFICIENT_VRAM",
                    details={"model_name": model_name, "required_min_vram_gb": min_vram, "available_vram_gb": available_vram_gb}
                )

        # 3. GPU compatibility check
        if gpu_name:
            compat_gpus = model_info.get("compatible_gpus", [])
            if compat_gpus:
                gpu_clean = gpu_name.lower()
                is_compat = any(cg.lower() in gpu_clean or gpu_clean in cg.lower() for cg in compat_gpus)
                if not is_compat:
                    raise ModelValidationError(
                        f"GPU '{gpu_name}' is not in the validated compatibility list for model '{model_name}'. Supported: {compat_gpus}",
                        error_code="GPU_NOT_SUPPORTED",
                        details={"model_name": model_name, "gpu_name": gpu_name, "compatible_gpus": compat_gpus}
                    )

    def list_models_by_task(self, task_type: str) -> List[Dict[str, Any]]:
        """Filters models that support a specific task type (e.g. 'image_generation', 'video_generation', 'text_to_speech')."""
        task_clean = task_type.lower().strip()
        matched = []
        for m in self.list_models():
            tasks = [t.lower() for t in m.get("task_types", [])] + [c.lower() for c in m.get("capabilities", [])]
            if task_clean in tasks or any(task_clean in t for t in tasks):
                matched.append(m)
        return matched

    def list_models_by_family(self, family: str) -> List[Dict[str, Any]]:
        """Filters models by family identifier (e.g. 'zimage', 'flux2', 'ltx', 'minimax')."""
        fam_clean = family.lower().strip()
        return [m for m in self.list_models() if m.get("family", "").lower() == fam_clean]

    def find_best_model_for_task(
        self,
        task_type: str,
        available_vram_gb: Optional[float] = None,
        prefer_fast: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Selects the optimal registered model for a given task based on VRAM constraints.
        Priority:
          - Image generation: zimage_turbo (fast MVP) -> flux2_klein_4b_fp8 -> sd15_base
          - Video generation: ltx_video (fast/iterative) -> minimax_h3 (multimodal heavy)
          - Upscaling: seedvr2_upscale
          - Voice: qwen3_tts
          - Lipsync: comfyui_float
        """
        candidates = self.list_models_by_task(task_type)
        if not candidates:
            return None

        # Filter by VRAM constraint if provided
        if available_vram_gb is not None:
            candidates = [m for m in candidates if m.get("min_vram_gb", 0.0) <= available_vram_gb]

        if not candidates:
            return None

        # Priority sorting rules
        task_norm = task_type.lower()
        if "image" in task_norm or "txt2img" in task_norm:
            priority_order = ["zimage_turbo", "flux2_klein_4b_fp8", "flux1_schnell_fp8", "sd15_base"]
            for pid in priority_order:
                for c in candidates:
                    if c.get("model_id") == pid:
                        return c

        elif "video" in task_norm or "i2v" in task_norm or "t2v" in task_norm:
            priority_order = ["ltx_video", "minimax_h3", "wan22_i2v"]
            for pid in priority_order:
                for c in candidates:
                    if c.get("model_id") == pid:
                        return c

        elif "upscale" in task_norm or "super_resolution" in task_norm:
            for c in candidates:
                if "seedvr2" in c.get("model_id", ""):
                    return c

        elif "tts" in task_norm or "speech" in task_norm or "voice" in task_norm:
            for c in candidates:
                if "qwen3" in c.get("model_id", ""):
                    return c

        elif "lipsync" in task_norm:
            for c in candidates:
                if "float" in c.get("model_id", ""):
                    return c

        return candidates[0]

    def get_optimal_resolution(self, model_id: str, aspect_ratio: str = "9:16") -> Tuple[int, int]:
        """
        Determines the optimal (width, height) resolution for a model and aspect ratio.
        Prevents Out-Of-Memory while maximizing fidelity.
        """
        model = self.get_model(model_id) or {}
        presets = model.get("resolution_presets", {})

        ar_clean = aspect_ratio.strip().lower().replace(":", "_")
        key = f"portrait_{ar_clean}" if "9_16" in ar_clean else f"landscape_{ar_clean}" if "16_9" in ar_clean else "square_1_1"

        if key in presets:
            return tuple(presets[key])

        # Fallback defaults based on family
        family = model.get("family", "").lower()
        if "sd15" in family:
            if "9_16" in ar_clean:
                return (512, 912)
            if "16_9" in ar_clean:
                return (912, 512)
            return (512, 512)

        # FLUX / Z-Image / SDXL
        if "9_16" in ar_clean:
            return (832, 1472)
        if "16_9" in ar_clean:
            return (1472, 832)
        return (1024, 1024)


# Global singleton
model_registry = ModelRegistry()


