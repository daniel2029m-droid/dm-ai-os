"""
Phase 14.4 Test Suite: Model Registry & Pre-dispatch Validation.
Validates:
- Valid model registration and metadata lookup.
- MODEL_NOT_REGISTERED rejection.
- MODEL_WORKFLOW_INCOMPATIBLE rejection.
- INSUFFICIENT_VRAM rejection.
- GPU_NOT_SUPPORTED rejection.
- Corrupted and empty config file resilience.
- Pre-dispatch gate blocking GPU submission when validation fails.
"""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.core.model_registry import ModelRegistry, ModelValidationError, model_registry
from src.core.creative_engine import CreativeEngine

def test_model_registry_valid_lookup():
    """Validates that registered models load correctly with full metadata."""
    models = model_registry.list_models()
    assert len(models) >= 3
    
    flux = model_registry.get_model("flux2_klein")
    assert flux is not None
    assert flux["architecture"] == "flux"
    assert flux["min_vram_gb"] == 12.0
    assert "flux2_klein_txt2img" in flux["compatible_workflows"]

    sd15 = model_registry.get_model("sd15_base")
    assert sd15 is not None
    assert sd15["min_vram_gb"] == 4.0

def test_model_not_registered_error():
    """Validates that non-existent models raise MODEL_NOT_REGISTERED."""
    with pytest.raises(ModelValidationError) as excinfo:
        model_registry.validate_model("non_existent_super_model_xyz")
    assert excinfo.value.error_code == "MODEL_NOT_REGISTERED"

def test_model_workflow_incompatible_error():
    """Validates that using a model with an incompatible workflow is rejected."""
    with pytest.raises(ModelValidationError) as excinfo:
        model_registry.validate_model("sd15_base", workflow_name="wan22_i2v")
    assert excinfo.value.error_code == "MODEL_WORKFLOW_INCOMPATIBLE"

def test_insufficient_vram_error():
    """Validates that insufficient GPU VRAM raises INSUFFICIENT_VRAM."""
    with pytest.raises(ModelValidationError) as excinfo:
        model_registry.validate_model("flux2_klein", available_vram_gb=8.0)
    assert excinfo.value.error_code == "INSUFFICIENT_VRAM"

def test_gpu_not_supported_error():
    """Validates that incompatible GPU architecture raises GPU_NOT_SUPPORTED."""
    with pytest.raises(ModelValidationError) as excinfo:
        model_registry.validate_model("flux2_klein", gpu_name="Intel HD Graphics 4000")
    assert excinfo.value.error_code == "GPU_NOT_SUPPORTED"

def test_corrupted_registry_resilience(tmp_path):
    """Validates graceful handling of corrupted registry JSON."""
    bad_json_file = tmp_path / "corrupt_registry.json"
    bad_json_file.write_text("{this is corrupted json", encoding="utf-8")
    
    reg = ModelRegistry(config_path=str(bad_json_file))
    models = reg.list_models()
    assert models == []
    assert reg.get_model("flux2_klein") is None

def test_empty_registry_resilience(tmp_path):
    """Validates graceful handling of empty registry config."""
    empty_file = tmp_path / "empty_registry.json"
    empty_file.write_text("{}", encoding="utf-8")
    
    reg = ModelRegistry(config_path=str(empty_file))
    assert reg.list_models() == []

@pytest.mark.asyncio
async def test_pre_dispatch_blocks_invalid_model():
    """Validates that CreativeEngine blocks invalid model prior to calling ComfyUI."""
    engine = CreativeEngine()
    
    # Incompatible model
    res = await engine.run_workflow(
        template_name_or_path="flux2_klein_txt2img",
        prompt="A photo of a robot",
        parameters={"model": "sd15_base"}  # sd15 is incompatible with flux workflow
    )
    assert res["status"] == "FAILED"
    assert res["error_code"] == "MODEL_WORKFLOW_INCOMPATIBLE"

@pytest.mark.asyncio
async def test_pre_dispatch_blocks_insufficient_vram():
    """Validates that CreativeEngine blocks dispatch when available VRAM is too low."""
    engine = CreativeEngine()
    
    res = await engine.run_workflow(
        template_name_or_path="flux2_klein_txt2img",
        prompt="A photo of a futuristic vehicle",
        parameters={"model": "flux2_klein", "vram_gb": 6.0}  # requires 12 GB
    )
    assert res["status"] == "FAILED"
    assert res["error_code"] == "INSUFFICIENT_VRAM"
