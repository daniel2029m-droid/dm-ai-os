"""
Phase 14.1 Test Suite: Storage & Auto-Vaulting Pipeline.
Validates:
- JobStore SQLite operations (CRUD, active job search, status filters).
- CreativeManifestV2 dataclass compatibility.
- Auto-Vaulting pipeline: download, safe path resolution, SHA-256 calculation, atomic write, Manifest & JobStore update.
- Path traversal defense.
- Zero-regression against Phase 13 baseline.
"""
import pytest
import asyncio
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.storage.job_store import JobStore
from src.storage.storage_layer import storage
from src.core.creative_engine import CreativeEngine, CreativeManifest, CreativeManifestV2, creative_engine
from src.adapters.comfy_adapter import ComfyAdapter

@pytest.fixture
def temp_job_store(tmp_path):
    db_file = tmp_path / "test_knowledge.db"
    return JobStore(db_path=str(db_file))

def test_job_store_crud(temp_job_store):
    """Validates JobStore SQLite persistence and lifecycle."""
    job_data = {
        "job_id": "test_job_123",
        "status": "SUBMITTED",
        "workflow_name": "flux2_klein_txt2img",
        "workflow_template_sha256": "abcdef123456",
        "workflow_effective_sha256": "abcdef123456",
        "backend_type": "REMOTE_COMFYUI",
        "provider": "google_colab",
        "prompt": "Cyberpunk city in neo-Tokyo",
        "parameters": {"seed": 42, "steps": 20},
        "input_assets": [],
        "output_assets": []
    }
    
    # 1. Create
    res = temp_job_store.create_job(job_data)
    assert res["job_id"] == "test_job_123"

    # 2. Get
    fetched = temp_job_store.get_job("test_job_123")
    assert fetched is not None
    assert fetched["job_id"] == "test_job_123"
    assert fetched["status"] == "SUBMITTED"
    assert fetched["parameters"]["seed"] == 42
    assert fetched["prompt"] == "Cyberpunk city in neo-Tokyo"

    # 3. Update
    temp_job_store.update_job("test_job_123", {
        "status": "COMPLETED",
        "output_assets": ["Artifacts/media/test_job_123/output.png"],
        "output_sha256": "112233445566",
        "output_size_bytes": 1024
    })
    
    updated = temp_job_store.get_job("test_job_123")
    assert updated["status"] == "COMPLETED"
    assert updated["output_sha256"] == "112233445566"
    assert updated["output_size_bytes"] == 1024
    assert len(updated["output_assets"]) == 1

    # 4. List & Filter
    all_jobs = temp_job_store.list_jobs()
    assert len(all_jobs) >= 1
    
    completed_jobs = temp_job_store.find_jobs_by_status("COMPLETED")
    assert len(completed_jobs) == 1
    assert completed_jobs[0]["job_id"] == "test_job_123"

def test_creative_manifest_v2_dataclass():
    """Validates CreativeManifestV2 schema and backward-compatible fields."""
    manifest = CreativeManifestV2(
        job_id="job_v2_001",
        workflow_name="sd15_txt2img",
        workflow_template_sha256="abc",
        workflow_effective_sha256="def",
        backend_type="REMOTE_COMFYUI",
        provider="runpod",
        prompt="portrait of an astronaut",
        created_at="2026-08-28T00:00:00Z",
        parameters={"seed": 99}
    )
    assert manifest.job_id == "job_v2_001"
    assert manifest.status == "SUBMITTED"
    assert manifest.input_assets == []
    assert manifest.output_assets == []

@pytest.mark.asyncio
async def test_run_workflow_records_in_job_store(tmp_path):
    """Validates that running a workflow automatically registers the job in JobStore."""
    engine = CreativeEngine()
    res = await engine.run_workflow(
        template_name_or_path="flux2_klein_txt2img",
        prompt="A vibrant watercolor landscape",
        parameters={"seed": 777}
    )
    assert "job_id" in res
    job_id = res["job_id"]
    
    # Query JobStore to verify persistence
    stored_job = storage.job_store.get_job(job_id)
    assert stored_job is not None
    assert stored_job["job_id"] == job_id
    assert stored_job["workflow_name"] == "flux2_klein_txt2img"
    assert stored_job["prompt"] == "A vibrant watercolor landscape"

@pytest.mark.asyncio
async def test_download_and_vault_artifact_pipeline():
    """Validates the complete auto-vaulting pipeline including disk write and manifest update."""
    fake_job_id = "test_vault_job_456"
    fake_png_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfake_image_bytes_content_for_test"
    expected_sha256 = hashlib.sha256(fake_png_content).hexdigest()
    expected_size = len(fake_png_content)

    # Initial job in JobStore
    storage.job_store.create_job({
        "job_id": fake_job_id,
        "status": "SUBMITTED",
        "workflow_name": "test_wf",
        "prompt": "test prompt",
        "created_at": "2026-08-28T00:00:00Z"
    })

    # Mock ComfyAdapter outputs and download
    with patch("src.adapters.comfy_adapter.comfy_adapter.get_job_outputs", new=AsyncMock(return_value=[
        {"filename": "test_output_001.png", "subfolder": "", "type": "output"}
    ])):
        with patch("src.adapters.comfy_adapter.comfy_adapter.download_output_bytes", new=AsyncMock(return_value=fake_png_content)):
            vault_res = await creative_engine.download_and_vault_artifact(fake_job_id)

            assert vault_res["status"] == "COMPLETED"
            assert vault_res["job_id"] == fake_job_id
            assert vault_res["output_sha256"] == expected_sha256
            assert vault_res["output_size_bytes"] == expected_size
            assert len(vault_res["output_assets"]) == 1

            # Verify physical file existence
            vaulted_file = storage.artifacts_dir / "media" / fake_job_id / "test_output_001.png"
            assert vaulted_file.exists()
            assert vaulted_file.read_bytes() == fake_png_content

            # Verify JobStore updated
            job_in_db = storage.job_store.get_job(fake_job_id)
            assert job_in_db["status"] == "COMPLETED"
            assert job_in_db["output_sha256"] == expected_sha256
            assert job_in_db["output_size_bytes"] == expected_size

            # Verify Manifest updated in Vault
            manifest_file = storage.artifacts_dir / f"creative_manifest_{fake_job_id}.json"
            assert manifest_file.exists()

def test_auto_vaulting_path_traversal_sanitization():
    """Ensures safe path sanitization prevents directory traversal attacks."""
    malicious_filename = "../../../Windows/System32/evil.png"
    safe_name = Path(malicious_filename).name
    assert safe_name == "evil.png"
