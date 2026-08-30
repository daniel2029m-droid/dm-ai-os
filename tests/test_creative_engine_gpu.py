"""
DM AI OS — Remote GPU Creative Engine Test Suite
================================================
Comprehensive unit & integration tests covering:
  - ModelRegistry catalog (Z-Image Turbo, FLUX.2, LTX, H3, SeedVR2, Qwen3-TTS, FLOAT, SD15).
  - ModelRouter authority (Pachu guardrail, remote GPU routing, REQUIRES_ACTIVATION).
  - CloudAssetStorage (Google One 5 TB canonical tree & cache sync).
  - WorkflowRegistry task mappings.
  - CreativeEngine high-level methods (generate, upscale, video, tts, lipsync).
  - MCP Creative Tools.
"""

import os
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.core.model_registry import model_registry, ModelValidationError
from src.core.model_router import model_router, ExecutionTarget
from src.storage.cloud_asset_storage import CloudAssetStorage, CANONICAL_TREE
from src.core.workflow_registry import workflow_registry, CreativeTask
from src.core.creative_engine import creative_engine
from src.providers.worker_registry import worker_registry, WorkerStatus
from src.mcp.tools import (
    creative_list_models,
    creative_get_model_capabilities,
    creative_list_workers,
    creative_worker_status,
    creative_submit_job
)


# ── 1. ModelRegistry Tests ─────────────────────────────────────────────

def test_model_registry_loads_all_creative_models():
    models = model_registry.list_models()
    model_ids = {m["model_id"] for m in models}
    
    expected_models = {
        "sd15_base",
        "zimage_turbo",
        "flux2_klein_4b_fp8",
        "flux1_schnell_fp8",
        "ltx_video",
        "minimax_h3",
        "seedvr2_upscale",
        "qwen3_tts",
        "comfyui_float"
    }
    assert expected_models.issubset(model_ids), f"Missing models in registry: {expected_models - model_ids}"


def test_model_registry_zimage_turbo_metadata():
    zimage = model_registry.get_model("zimage_turbo")
    assert zimage is not None
    assert zimage["family"] == "zimage"
    assert zimage["min_vram_gb"] == 8.0
    assert zimage["recommended_vram_gb"] == 12.0
    assert zimage["local_allowed"] is False
    assert zimage["remote_gpu_allowed"] is True
    assert "image_generation" in zimage["task_types"]


def test_model_registry_query_by_task():
    image_models = model_registry.list_models_by_task("image_generation")
    image_ids = {m["model_id"] for m in image_models}
    assert "zimage_turbo" in image_ids
    assert "sd15_base" in image_ids

    video_models = model_registry.list_models_by_task("video_generation")
    video_ids = {m["model_id"] for m in video_models}
    assert "ltx_video" in video_ids
    assert "minimax_h3" in video_ids


def test_model_registry_find_best_model_for_task():
    best_img = model_registry.find_best_model_for_task("image_generation")
    assert best_img is not None
    assert best_img["model_id"] == "zimage_turbo"

    best_vid = model_registry.find_best_model_for_task("video_generation")
    assert best_vid is not None
    assert best_vid["model_id"] == "ltx_video"

    best_upscale = model_registry.find_best_model_for_task("image_upscale")
    assert best_upscale is not None
    assert best_upscale["model_id"] == "seedvr2_upscale"


# ── 2. ModelRouter Tests (Pachu Guardrail) ─────────────────────────────

def test_model_router_pachu_guardrail_blocks_heavy_visual_models():
    """Pachu with iGPU must NEVER execute heavy visual models locally."""
    with patch.object(worker_registry, "get_active_worker", return_value=None):
        decision = model_router.route_intent(task_type="image_generation", prompt="test cat")
        assert decision.target == ExecutionTarget.REQUIRES_ACTIVATION
        assert "GPU worker offline" in decision.reason
        assert decision.activation_url is not None


def test_model_router_routes_to_remote_gpu_when_worker_ready():
    mock_worker = {
        "worker_id": "colab-t4-primary",
        "session_id": "rt-colab-12345",
        "gpu_name": "Tesla T4",
        "vram_gb": 16.0,
        "status": WorkerStatus.READY.value,
        "endpoint": "https://test-worker.trycloudflare.com"
    }
    with patch.object(worker_registry, "get_active_worker", return_value=mock_worker):
        decision = model_router.route_intent(task_type="image_generation", model_name="zimage_turbo")
        assert decision.target == ExecutionTarget.REMOTE_GPU
        assert decision.worker["worker_id"] == "colab-t4-primary"
        assert decision.model_id == "zimage_turbo"


def test_model_router_allows_lightweight_local_text():
    decision = model_router.route_intent(task_type="text_reasoning", prompt="2+2")
    assert decision.target == ExecutionTarget.LOCAL


def test_model_router_capability_matrix():
    matrix_data = model_router.get_capability_matrix()
    assert "models" in matrix_data
    assert len(matrix_data["models"]) >= 8
    
    zimage_entry = next(m for m in matrix_data["models"] if m["model_id"] == "zimage_turbo")
    assert zimage_entry["pachu_compatible"] is False
    assert zimage_entry["t4_16gb_compatible"] is True


# ── 3. CloudAssetStorage Tests ─────────────────────────────────────────

def test_cloud_asset_storage_structure_creation():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = CloudAssetStorage(root_path=tmpdir)
        assert storage.is_mounted() is True
        res = storage.ensure_structure()
        
        for section in CANONICAL_TREE:
            assert res[section] is True
            assert (Path(tmpdir) / section).exists()


def test_cloud_asset_storage_find_and_cache_sync():
    with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_cache:
        storage = CloudAssetStorage(root_path=tmp_root)
        storage.ensure_structure()
        
        # Create dummy model file
        dummy_model = Path(tmp_root) / "AI_LIBRARY/IMAGE/Z-IMAGE/zimage_turbo_v1.safetensors"
        dummy_model.write_bytes(b"dummy_weights_data_1234567890")
        
        found = storage.find_model_file("zimage_turbo_v1.safetensors")
        assert found == dummy_model
        
        # Sync to cache
        success, cache_path, msg = storage.sync_to_worker_cache(dummy_model, Path(tmp_cache))
        assert success is True
        assert cache_path.exists()
        assert cache_path.read_bytes() == b"dummy_weights_data_1234567890"
        
        # Second sync should be cache hit
        success2, cache_path2, msg2 = storage.sync_to_worker_cache(dummy_model, Path(tmp_cache))
        assert success2 is True
        assert "Cache hit" in msg2


# ── 4. WorkflowRegistry Tests ──────────────────────────────────────────

def test_workflow_registry_selects_zimage_by_default_for_txt2img():
    wf = workflow_registry.select_workflow(task=CreativeTask.IMAGE_TXT2IMG)
    assert wf["template"] == "zimage_turbo_txt2img"
    assert wf["min_vram_gb"] <= 16.0


def test_workflow_registry_selects_sd15_when_explicitly_requested():
    wf = workflow_registry.select_workflow(task=CreativeTask.IMAGE_TXT2IMG, preferred_model="sd15_base")
    assert wf["template"] == "sd15_txt2img"


def test_workflow_registry_selects_ltx_for_video():
    wf = workflow_registry.select_workflow(task=CreativeTask.VIDEO_TXT2VID)
    assert wf["template"] == "ltx_txt2video"


def test_workflow_registry_selects_seedvr2_for_upscale():
    wf = workflow_registry.select_workflow(task=CreativeTask.IMAGE_UPSCALE)
    assert wf["template"] == "seedvr2_upscale"


# ── 5. CreativeEngine High-Level Intent Tests ─────────────────────────

@pytest.mark.asyncio
async def test_creative_engine_submit_returns_requires_activation_when_gpu_offline():
    with patch.object(worker_registry, "get_active_worker", return_value=None):
        res = await creative_engine.submit_generation_job(
            task_type="image_generation",
            prompt="cyberpunk city street",
            model_name="zimage_turbo"
        )
        assert res["status"] == "REQUIRES_ACTIVATION"
        assert res["target"] == "REQUIRES_ACTIVATION"
        assert "Google Colab" in res["instructions"]
        assert "colab" in res["activation_url"]


@pytest.mark.asyncio
async def test_creative_engine_generate_convenience_method():
    with patch.object(worker_registry, "get_active_worker", return_value=None):
        res = await creative_engine.generate(prompt="beautiful landscape", model="zimage_turbo")
        assert res["status"] == "REQUIRES_ACTIVATION"


# ── 6. MCP Creative Tools Tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_creative_list_models():
    models = await creative_list_models()
    assert isinstance(models, list)
    assert len(models) >= 8
    
    zimage_m = await creative_list_models(task_type="image_generation")
    assert any(m["model_id"] == "zimage_turbo" for m in zimage_m)


@pytest.mark.asyncio
async def test_mcp_creative_get_model_capabilities():
    caps = await creative_get_model_capabilities()
    assert "models" in caps
    assert "worker_status" in caps


@pytest.mark.asyncio
async def test_mcp_creative_worker_status():
    status = await creative_worker_status()
    assert "state" in status
    assert "backend" in status


@pytest.mark.asyncio
async def test_mcp_creative_submit_job_fallback():
    with patch.object(worker_registry, "get_active_worker", return_value=None):
        res = await creative_submit_job(task_type="image_generation", prompt="test mcp")
        assert res["status"] == "REQUIRES_ACTIVATION"


# ── 7. User Outputs Library & Remote Preview Tests ─────────────────────

def test_user_outputs_manager_export_image():
    from src.storage.user_outputs import UserOutputsManager
    with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_user:
        dummy_file = Path(tmp_root) / "test_image.png"
        dummy_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtest_data")
        
        manager = UserOutputsManager(root_dir=tmp_user)
        success, dest, msg = manager.export_asset(
            vault_file=dummy_file,
            job_id="test_job_123",
            workflow_name="zimage_turbo_txt2img"
        )
        assert success is True
        assert dest is not None
        assert dest.exists()
        assert "IMAGENES" in str(dest)
        
        listed = manager.list_user_outputs()
        assert len(listed["categories"]["IMAGENES"]) == 1
        assert listed["categories"]["IMAGENES"][0]["filename"] == "test_image.png"


def test_user_outputs_manager_categorizes_video():
    from src.storage.user_outputs import UserOutputsManager
    with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_user:
        dummy_video = Path(tmp_root) / "test_clip.mp4"
        dummy_video.write_bytes(b"\x00\x00\x00\x18ftypmp42video_data")
        
        manager = UserOutputsManager(root_dir=tmp_user)
        success, dest, msg = manager.export_asset(
            vault_file=dummy_video,
            job_id="test_vid_123",
            workflow_name="ltx_txt2video"
        )
        assert success is True
        assert "VIDEOS" in str(dest)
        assert dest.exists()


@pytest.mark.asyncio
async def test_mcp_creative_list_user_outputs():
    from src.mcp.tools import creative_list_user_outputs
    res = await creative_list_user_outputs()
    assert "root_dir" in res
    assert "categories" in res
    assert "IMAGENES" in res["categories"]
    assert "VIDEOS" in res["categories"]


def test_signed_urls_generation_for_remote_clients():
    from src.api.creative_assets_router import generate_signed_urls, verify_asset_signature
    with patch.dict(os.environ, {"DM_MEDIA_SIGNING_SECRET": "test_secret_key_1234567890"}):
        urls = generate_signed_urls(job_id="job_remote_999", ttl=600, base_url="https://ai.dmorales.com.ar")
        assert urls["job_id"] == "job_remote_999"
        assert "https://ai.dmorales.com.ar/api/v1/creative/assets/job_remote_999/view" in urls["view_url"]
        assert "https://ai.dmorales.com.ar/api/v1/creative/assets/job_remote_999/download" in urls["download_url"]
        assert "sig=" in urls["view_url"]
        assert "exp=" in urls["view_url"]

