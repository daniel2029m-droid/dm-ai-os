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

        return model_info

# Global singleton
model_registry = ModelRegistry()
