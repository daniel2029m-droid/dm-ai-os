"""
Unit Tests for RunPod Network Volume Infrastructure & Model Setup — DM AI OS
=============================================================================
Tests:
1. verify_workspace_mount: Success write test & failure handling
2. ensure_model_directories: Hierarchy creation for unet, clip, vae, etc.
3. configure_extra_model_paths: YAML formatting and container root writing
4. setup_safe_symlinks: Non-destructive symlink creation
5. check_model_presence: Existence and minimum size validation
6. download_model_file & skip logic: Avoids duplicate downloads
7. run_setup_pipeline: End-to-end setup orchestration
8. verify_flux2_models_present: Remote object_info loader discovery parsing
9. Datacenter compatibility & strict US-TX-3 volume binding
10. MODEL_DOWNLOAD_REQUIRES_EXPLICIT_AUTHORIZATION guardrail check
"""

import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.config.runpod_config import runpod_config
from src.adapters.runpod_adapter import RunPodAdapter, RunPodAdapterError, runpod_adapter
from scripts.setup_runpod_models import (
    verify_workspace_mount,
    ensure_model_directories,
    configure_extra_model_paths,
    setup_safe_symlinks,
    check_model_presence,
    download_model_file,
    run_setup_pipeline,
    FLUX2_MODELS,
)


@pytest.fixture
def tmp_workspace(tmp_path):
    """Provide a clean temporary directory mocking /workspace."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    comfy = ws / "ComfyUI"
    comfy.mkdir()
    return ws


# ── 1. Workspace Mount & Write Test ─────────────────────────────

def test_verify_workspace_mount_success(tmp_workspace):
    """Test verify_workspace_mount succeeds when directory exists and is writable."""
    assert verify_workspace_mount(tmp_workspace) is True
    # Ensure temporary file was removed
    assert not (tmp_workspace / ".mount_test_tmp").exists()


def test_verify_workspace_mount_missing(tmp_path):
    """Test verify_workspace_mount raises RuntimeError when directory missing."""
    missing_dir = tmp_path / "non_existent_workspace"
    with pytest.raises(RuntimeError, match="is not mounted"):
        verify_workspace_mount(missing_dir)


def test_verify_workspace_mount_read_only(tmp_path):
    """Test verify_workspace_mount raises RuntimeError when write fails."""
    readonly_dir = tmp_path / "readonly_workspace"
    readonly_dir.mkdir()
    with patch.object(Path, "write_text", side_effect=OSError("Permission denied")):
        with pytest.raises(RuntimeError, match="write failure"):
            verify_workspace_mount(readonly_dir)


# ── 2. Directory Hierarchy Creation ─────────────────────────────

def test_ensure_model_directories(tmp_workspace):
    """Test creation of required model directory hierarchy."""
    comfy_base = tmp_workspace / "ComfyUI"
    dirs = ensure_model_directories(comfy_base)

    assert dirs["unet"] == comfy_base / "models" / "unet"
    assert dirs["clip"] == comfy_base / "models" / "clip"
    assert dirs["vae"] == comfy_base / "models" / "vae"
    assert dirs["diffusion_models"] == comfy_base / "models" / "diffusion_models"
    assert dirs["checkpoints"] == comfy_base / "models" / "checkpoints"

    for p in dirs.values():
        assert p.exists() and p.is_dir()


# ── 3. extra_model_paths.yaml Generation ────────────────────────

def test_configure_extra_model_paths(tmp_path):
    """Test extra_model_paths.yaml generation and target writing."""
    root1 = tmp_path / "ComfyUI"
    root2 = tmp_path / "root" / "ComfyUI"

    yaml_content = configure_extra_model_paths(container_roots=[root1, root2])

    assert "base_path: /workspace/ComfyUI/models" in yaml_content
    assert "unet: unet" in yaml_content
    assert "clip: clip" in yaml_content
    assert "vae: vae" in yaml_content

    assert (root1 / "extra_model_paths.yaml").exists()
    assert (root2 / "extra_model_paths.yaml").exists()


# ── 4. Safe Symlinks ───────────────────────────────────────────

def test_setup_safe_symlinks(tmp_path):
    """Test non-destructive symlink creation from workspace to ComfyUI roots."""
    ws_models = tmp_path / "workspace" / "ComfyUI" / "models"
    unet_ws = ws_models / "unet"
    unet_ws.mkdir(parents=True)
    fake_model = unet_ws / "flux-2-klein-4b-fp8.safetensors"
    fake_model.write_bytes(b"0" * 100)

    comfy_root = tmp_path / "ComfyUI"
    comfy_models = comfy_root / "models"
    comfy_models.mkdir(parents=True)

    with patch.object(Path, "symlink_to") as mock_symlink:
        symlinks = setup_safe_symlinks(
            container_roots=[comfy_root],
            workspace_base=ws_models
        )
        assert len(symlinks) == 1
        mock_symlink.assert_called_once()


# ── 5. Model Presence & Size Validation ────────────────────────

def test_check_model_presence(tmp_path):
    """Test check_model_presence for valid, missing, and undersized files."""
    dest = tmp_path / "test_model.safetensors"

    # Missing
    is_valid, size = check_model_presence(dest, min_size_gb=1.0)
    assert is_valid is False
    assert size == 0.0

    # Undersized (100 MB < 1 GB)
    dest.write_bytes(b"0" * (100 * 1024 * 1024))
    is_valid, size = check_model_presence(dest, min_size_gb=1.0)
    assert is_valid is False
    assert size < 0.2

    # Valid (1 GB)
    with patch.object(Path, "stat") as mock_stat:
        mock_stat_val = MagicMock()
        mock_stat_val.st_size = int(1.1 * 1024**3)
        mock_stat.return_value = mock_stat_val
        is_valid, size = check_model_presence(dest, min_size_gb=1.0)
        assert is_valid is True
        assert size >= 1.0


# ── 6. Download & Duplicate Skip Logic ─────────────────────────

def test_download_model_file_skip_existing(tmp_path):
    """Test download_model_file skips downloading when valid file is present."""
    model_dirs = {"unet": tmp_path / "unet", "diffusion_models": tmp_path / "diffusion_models"}
    for p in model_dirs.values():
        p.mkdir()

    dest = model_dirs["unet"] / "flux-2-klein-4b-fp8.safetensors"
    dest.write_bytes(b"0" * 10)

    with patch("scripts.setup_runpod_models.check_model_presence") as mock_check:
        mock_check.return_value = (True, 4.07)
        success, reason = download_model_file(
            "flux-2-klein-4b-fp8.safetensors",
            "unet",
            "http://example.com/model.safetensors",
            4.0,
            model_dirs
        )
        assert success is True
        assert reason == "SKIPPED_EXISTING"


# ── 7. Setup Pipeline Orchestrator ──────────────────────────────

def test_run_setup_pipeline_orchestration(tmp_workspace):
    """Test full setup pipeline orchestration with mocked model files."""
    comfy_base = tmp_workspace / "ComfyUI"

    with patch("scripts.setup_runpod_models.verify_workspace_mount", return_value=True), \
         patch("scripts.setup_runpod_models.check_model_presence", return_value=(True, 4.0)):

        result = run_setup_pipeline(
            pipeline="flux2",
            base_dir=comfy_base,
            perform_downloads=False
        )

        assert result["status"] == "SUCCESS"
        assert result["workspace_mounted"] is True
        assert len(result["skipped"]) == len(FLUX2_MODELS)
        assert len(result["failed"]) == 0


# ── 8. ComfyUI /object_info Discovery Verification ──────────────

@pytest.mark.asyncio
async def test_verify_flux2_models_present_success():
    """Test verify_flux2_models_present parses loader nodes correctly."""
    adapter = RunPodAdapter()

    mock_object_info = {
        "UNETLoader": {
            "input": {"required": {"unet_name": [["flux-2-klein-4b-fp8.safetensors"]]}}
        },
        "DualCLIPLoader": {
            "input": {"required": {"clip_name1": [["clip_l.safetensors", "t5xxl_fp8_e4m3fn.safetensors"]]}}
        },
        "VAELoader": {
            "input": {"required": {"vae_name": [["ae.safetensors"]]}}
        }
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_object_info

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_get.return_value = mock_response
        res = await adapter.verify_flux2_models_present("http://127.0.0.1:8188")
        assert res["status"] == "READY"
        assert res["ready"] is True
        assert res["missing_models"] == []


@pytest.mark.asyncio
async def test_verify_flux2_models_present_missing():
    """Test verify_flux2_models_present detects missing model files."""
    adapter = RunPodAdapter()

    mock_object_info = {
        "VAELoader": {"input": {"required": {"vae_name": [["pixel_space"]]}}}
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_object_info

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_get.return_value = mock_response
        res = await adapter.verify_flux2_models_present("http://127.0.0.1:8188")
        assert res["status"] == "MODELS_MISSING"
        assert res["ready"] is False
        assert len(res["missing_models"]) == 4


# ── 9. Datacenter Binding & Cross-DC Fallback Blocking ──────────

@pytest.mark.asyncio
async def test_strict_datacenter_binding_and_cross_dc_blocking():
    """Test strict volume datacenter binding and cross-DC fallback blocking."""
    adapter = RunPodAdapter()

    mock_vol_info = {
        "status": "VALID",
        "is_valid": True,
        "volume_id": "tbupq29n08",
        "name": "DM-AI-OS-Models",
        "size_gb": 40,
        "dataCenterId": "US-TX-3"
    }

    with patch.object(adapter, "validate_network_volume_compatibility", new_callable=AsyncMock) as mock_vol, \
         patch.object(adapter, "_graphql_query", new_callable=AsyncMock) as mock_gql:
        mock_vol.return_value = mock_vol_info
        mock_gql.side_effect = Exception("No longer any instances available in community cloud")

        with pytest.raises(RunPodAdapterError) as exc_info:
            await adapter.create_pod(
                name="TestPod",
                gpu_type_id="NVIDIA GeForce RTX 4090",
                network_volume_id="tbupq29n08",
                cloud_type="COMMUNITY"
            )

        assert exc_info.value.status_code == 503
        assert "NETWORK_VOLUME_DATACENTER_UNAVAILABLE" in str(exc_info.value)


# ── 10. Guardrail Tests ─────────────────────────────────────────

def test_model_download_requires_explicit_authorization_guardrail():
    """Test MODEL_DOWNLOAD_REQUIRES_EXPLICIT_AUTHORIZATION guardrail setting."""
    assert runpod_config.model_download_requires_explicit_authorization is True


# ── 11. start_user.sh Hook Architecture Tests ──────────────────

def test_start_user_sh_content_generation():
    """Test get_start_user_sh_content generates valid bash script with required paths."""
    content = RunPodAdapter.get_start_user_sh_content()
    assert "#!/bin/bash" in content
    assert "/workspace/ComfyUI/models/unet" in content
    assert "extra_model_paths.yaml" in content
    assert "dm_ai_os_network_volume" in content
    assert "ln -s" in content


def test_phase1_write_start_user_sh_cmd():
    """Test get_phase1_write_start_user_sh_cmd generates executable Phase 1 command."""
    cmd = RunPodAdapter.get_phase1_write_start_user_sh_cmd()
    assert "bash -c" in cmd
    assert "/workspace/start_user.sh" in cmd
    assert "chmod +x" in cmd

