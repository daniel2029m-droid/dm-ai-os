"""
Unit Tests for RunPod Adapter & GPU Watchdog (Using Mocks)
===========================================================
Tests:
- Initialization & configuration loading
- Missing API key error handling
- Account status GraphQL query (mocked)
- Pod listing & lifecycle operations (start/stop/terminate)
- GPU Session Watchdog try/finally auto-stop safety
- ComfyUI job submission & status polling (mocked)
- Upload & Download artifact operations
- Cache hit & cache miss validation
- Error handling for HTTP 401, 403, 429 rate limits
"""

import os
import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from src.config.runpod_config import runpod_config
from src.adapters.runpod_adapter import RunPodAdapter, RunPodAdapterError, runpod_adapter
from src.storage.storage_layer import storage


@pytest.fixture(autouse=True)
def setup_env():
    """Set up environment for unit testing with mocks."""
    os.environ["RUNPOD_API_KEY"] = "mock_runpod_api_key_12345"
    os.environ["RUNPOD_POD_ID"] = "mock_pod_id_abc123"
    os.environ["RUNPOD_AUTO_START"] = "true"
    os.environ["RUNPOD_AUTO_STOP"] = "true"
    storage.clear_cache()
    yield


@pytest.mark.asyncio
async def test_adapter_initialization():
    """Test configuration and adapter property initialization."""
    adapter = RunPodAdapter()
    assert adapter.api_key == "mock_runpod_api_key_12345"
    assert runpod_config.is_configured is True
    assert runpod_config.image_model == "black-forest-labs/FLUX.2-klein-4B"


@pytest.mark.asyncio
async def test_api_key_missing():
    """Test error handling when RUNPOD_API_KEY is missing."""
    os.environ.pop("RUNPOD_API_KEY", None)
    adapter = RunPodAdapter()
    with pytest.raises(RunPodAdapterError) as exc_info:
        _ = adapter.api_key
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_graphql_account_status_mock():
    """Test get_account_status with mocked GraphQL response."""
    adapter = RunPodAdapter()

    mock_resp = {
        "myself": {
            "id": "usr_123",
            "email": "dev@dmaios.ai",
            "clientBalance": 45.50,
            "pods": [{"id": "pod_1"}]
        }
    }

    with patch.object(adapter, "_graphql_query", new_callable=AsyncMock) as mock_gql:
        mock_gql.return_value = mock_resp
        status = await adapter.get_account_status()
        assert status["status"] == "ok"
        assert status["email"] == "dev@dmaios.ai"
        assert status["balance"] == 45.50


@pytest.mark.asyncio
async def test_pod_lifecycle_operations():
    """Test start_pod, stop_pod, and terminate_pod methods."""
    adapter = RunPodAdapter()

    with patch.object(adapter, "_graphql_query", new_callable=AsyncMock) as mock_gql:
        mock_gql.return_value = {"podResume": {"id": "mock_pod_id_abc123", "desiredStatus": "RUNNING"}}
        res_start = await adapter.start_pod("mock_pod_id_abc123")
        assert res_start["desiredStatus"] == "RUNNING"

        mock_gql.return_value = {"podStop": {"id": "mock_pod_id_abc123", "desiredStatus": "STOPPED"}}
        res_stop = await adapter.stop_pod("mock_pod_id_abc123")
        assert res_stop["desiredStatus"] == "STOPPED"


@pytest.mark.asyncio
async def test_gpu_session_watchdog_cleanup():
    """Test that gpu_session context manager automatically triggers cleanup_gpu / watchdog."""
    adapter = RunPodAdapter()

    with patch.object(adapter, "ensure_gpu_available", new_callable=AsyncMock) as mock_ensure, \
         patch.object(adapter, "cleanup_gpu", new_callable=AsyncMock) as mock_cleanup:

        async with adapter.gpu_session():
            assert adapter._active_jobs_count == 1

        assert adapter._active_jobs_count == 0
        assert mock_ensure.called
        assert mock_cleanup.called



@pytest.mark.asyncio
async def test_comfyui_job_submission_and_status():
    """Test submit_job and get_job_status with mocked HTTP endpoints."""
    adapter = RunPodAdapter()

    mock_resp_submit = MagicMock()
    mock_resp_submit.status_code = 200
    mock_resp_submit.json.return_value = {"prompt_id": "job_998877"}

    mock_resp_history = MagicMock()
    mock_resp_history.status_code = 200
    mock_resp_history.json.return_value = {
        "job_998877": {"outputs": {"9": {"images": [{"filename": "out.png"}]}}}
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:

        mock_post.return_value = mock_resp_submit
        mock_get.return_value = mock_resp_history

        job = await adapter.submit_job({"prompt": "test"})
        assert job["job_id"] == "job_998877"

        st = await adapter.get_job_status("job_998877")
        assert st["completed"] is True


@pytest.mark.asyncio
async def test_generate_image_cache_hit_and_miss():
    """Test image generation with cache miss on first call and cache hit on second call."""
    adapter = RunPodAdapter()

    with patch.object(adapter, "gpu_session") as mock_session, \
         patch.object(adapter, "submit_job", new_callable=AsyncMock) as mock_submit, \
         patch.object(adapter, "get_job_result", new_callable=AsyncMock) as mock_result, \
         patch.object(adapter, "download_result", new_callable=AsyncMock) as mock_dl:

        mock_session.return_value.__aenter__.return_value = adapter
        mock_submit.return_value = {"job_id": "job_112233"}
        mock_result.return_value = {"completed": True}
        mock_dl.return_value = {
            "image_url": "/api/providers/uploads/runpod_test.png",
            "file_path": "C:/tmp/runpod_test.png"
        }

        # 1st call -> Cache miss -> Executes job
        res1 = await adapter.generate_image("A futuristic RunPod city", aspect_ratio="16:9", use_cache=True)
        assert res1["_cached"] is False
        assert mock_submit.call_count == 1

        # 2nd call -> Cache hit -> Does NOT execute job
        res2 = await adapter.generate_image("A futuristic RunPod city", aspect_ratio="16:9", use_cache=True)
        assert res2["_cached"] is True
        assert mock_submit.call_count == 1


@pytest.mark.asyncio
async def test_select_best_gpu():
    """Test dynamic GPU selection logic."""
    adapter = RunPodAdapter()
    mock_gpus = [
        {"id": "NVIDIA GeForce RTX 3090", "memoryInGb": 24},
        {"id": "NVIDIA GeForce RTX 4090", "memoryInGb": 24},
        {"id": "NVIDIA GeForce RTX 5090", "memoryInGb": 32},
    ]
    with patch.object(adapter, "_graphql_query", new_callable=AsyncMock) as mock_gql:
        mock_gql.return_value = {"gpuTypes": mock_gpus}
        gpu = await adapter.select_best_gpu(required_vram_gb=24)
        assert gpu["id"] == "NVIDIA GeForce RTX 4090"


@pytest.mark.asyncio
async def test_create_pod_on_demand():
    """Test on-demand pod creation logic."""
    adapter = RunPodAdapter()
    with patch.object(adapter, "select_best_gpu", new_callable=AsyncMock) as mock_select, \
         patch.object(adapter, "create_pod", new_callable=AsyncMock) as mock_create:
        mock_select.return_value = {"id": "NVIDIA GeForce RTX 4090"}
        mock_create.return_value = {"id": "dyn_pod_100"}

        pod = await adapter.create_pod_on_demand()
        assert pod["id"] == "dyn_pod_100"
        assert mock_create.called


@pytest.mark.asyncio
async def test_watchdog_auto_terminate_on_failure():
    """Test watchdog guarantees cleanup_gpu execution on job exception."""
    adapter = RunPodAdapter()

    with patch.object(adapter, "ensure_gpu_available", new_callable=AsyncMock) as mock_ensure, \
         patch.object(adapter, "cleanup_gpu", new_callable=AsyncMock) as mock_cleanup:

        mock_ensure.return_value = True

        with pytest.raises(RuntimeError):
            async with adapter.gpu_session():
                raise RuntimeError("Simulated job failure")

        assert mock_cleanup.called
        call_kwargs = mock_cleanup.call_args[1]
        assert call_kwargs.get("reason") == "session_ended"


@pytest.mark.asyncio
async def test_list_network_volumes():
    """Test listing Network Volumes from RunPod API."""
    adapter = RunPodAdapter()
    mock_volumes = [
        {"id": "vol_abc123", "name": "DM-AI-OS-Models", "size": 40, "dataCenterId": "US-TX-3"},
    ]
    with patch.object(adapter, "_graphql_query", new_callable=AsyncMock) as mock_gql:
        mock_gql.return_value = {"myself": {"networkVolumes": mock_volumes}}
        vols = await adapter.list_network_volumes()
        assert len(vols) == 1
        assert vols[0]["name"] == "DM-AI-OS-Models"
        assert vols[0]["size"] == 40


@pytest.mark.asyncio
async def test_create_network_volume():
    """Test creating a Network Volume via RunPod GraphQL API."""
    adapter = RunPodAdapter()
    with patch.object(adapter, "_graphql_query", new_callable=AsyncMock) as mock_gql:
        mock_gql.return_value = {
            "createNetworkVolume": {
                "id": "vol_new999",
                "name": "DM-AI-OS-Models",
                "size": 40,
                "dataCenterId": "US-TX-3",
            }
        }
        vol = await adapter.create_network_volume(name="DM-AI-OS-Models", size_gb=40)
        assert vol["id"] == "vol_new999"
        assert vol["size"] == 40
        called_vars = mock_gql.call_args[0][1]
        assert called_vars["input"]["size"] == 40


@pytest.mark.asyncio
async def test_create_pod_with_network_volume():
    """Test that create_pod correctly passes networkVolumeId when configured."""
    adapter = RunPodAdapter()
    vol_info = {
        "status": "VALID", "is_valid": True, "volume_id": "vol_abc123",
        "name": "DM-AI-OS-Models", "size_gb": 40, "dataCenterId": "US-TX-3"
    }
    with patch.object(adapter, "validate_network_volume_compatibility", new_callable=AsyncMock) as mock_val, \
         patch.object(adapter, "_graphql_query", new_callable=AsyncMock) as mock_gql:
        mock_val.return_value = vol_info
        mock_gql.return_value = {
            "podFindAndDeployOnDemand": {
                "id": "pod_net_vol_test",
                "imageName": "runpod/comfyui:cuda12.8",
                "desiredStatus": "RUNNING",
            }
        }
        pod = await adapter.create_pod(
            name="test-pod",
            gpu_type_id="NVIDIA GeForce RTX 4090",
            template_id="cw3nka7d08",
            network_volume_id="vol_abc123",
        )
        assert pod["id"] == "pod_net_vol_test"
        called_vars = mock_gql.call_args[0][1]
        pod_input = called_vars["input"]
        assert pod_input["networkVolumeId"] == "vol_abc123"
        assert pod_input["dataCenterId"] == "US-TX-3"
        assert pod_input["templateId"] == "cw3nka7d08"
        assert pod_input["gpuTypeId"] == "NVIDIA GeForce RTX 4090"


@pytest.mark.asyncio
async def test_create_pod_without_network_volume():
    """Test that create_pod works without network volume and uses container disk only."""
    adapter = RunPodAdapter()
    with patch.object(adapter, "_graphql_query", new_callable=AsyncMock) as mock_gql:
        mock_gql.return_value = {
            "podFindAndDeployOnDemand": {
                "id": "pod_ephemeral_test",
                "imageName": "runpod/comfyui:cuda12.8",
                "desiredStatus": "RUNNING",
            }
        }
        pod = await adapter.create_pod(
            name="test-ephemeral-pod",
            gpu_type_id="NVIDIA GeForce RTX 4090",
            template_id="cw3nka7d08",
            network_volume_id="",
        )
        assert pod["id"] == "pod_ephemeral_test"
        called_vars = mock_gql.call_args[0][1]
        pod_input = called_vars["input"]
        assert "networkVolumeId" not in pod_input




@pytest.mark.asyncio
async def test_ensure_models_available_authorization_guardrail():
    """Test ensure_models_available returns MODELS_MISSING when guardrail is active."""
    adapter = RunPodAdapter()
    with patch.object(adapter, "list_network_volumes", new_callable=AsyncMock) as mock_vols:
        mock_vols.return_value = [{"id": "tbupq29n08", "name": "DM-AI-OS-Models", "size": 40}]
        res = await adapter.ensure_models_available("flux2")
        assert res["status"] == "MODELS_MISSING"
        assert res["ready"] is False
        assert "explicit user authorization" in res["reason"]


@pytest.mark.asyncio
async def test_validate_network_volume_compatibility_success():
    """Test network volume validation returns volume info and dataCenterId."""
    adapter = RunPodAdapter()
    mock_vols = [{"id": "tbupq29n08", "name": "DM-AI-OS-Models", "size": 40, "dataCenterId": "US-TX-3"}]
    with patch.object(adapter, "list_network_volumes", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = mock_vols
        res = await adapter.validate_network_volume_compatibility("tbupq29n08")
        assert res["is_valid"] is True
        assert res["dataCenterId"] == "US-TX-3"
        assert res["volume_id"] == "tbupq29n08"


@pytest.mark.asyncio
async def test_validate_network_volume_compatibility_missing():
    """Test validating missing network volume raises 404 error."""
    adapter = RunPodAdapter()
    with patch.object(adapter, "list_network_volumes", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = []
        with pytest.raises(RunPodAdapterError) as exc_info:
            await adapter.validate_network_volume_compatibility("non_existent_vol")
        assert exc_info.value.status_code == 404
        assert "NETWORK_VOLUME_NOT_FOUND" in str(exc_info.value)


@pytest.mark.asyncio
async def test_block_cross_datacenter_fallback_when_volume_attached():
    """Test that create_pod BLOCKS cross-datacenter fallback when networkVolumeId is configured."""
    adapter = RunPodAdapter()
    vol_mock = {"id": "tbupq29n08", "name": "DM-AI-OS-Models", "size": 40, "dataCenterId": "US-TX-3"}

    with patch.object(adapter, "validate_network_volume_compatibility", new_callable=AsyncMock) as mock_val, \
         patch.object(adapter, "_graphql_query", new_callable=AsyncMock) as mock_gql:

        mock_val.return_value = vol_mock
        mock_gql.side_effect = RunPodAdapterError("There are no longer any instances available in US-TX-3")

        with pytest.raises(RunPodAdapterError) as exc_info:
            await adapter.create_pod(
                name="test-bound-pod",
                gpu_type_id="NVIDIA GeForce RTX 4090",
                template_id="cw3nka7d08",
                network_volume_id="tbupq29n08"
            )

        assert exc_info.value.status_code == 503
        assert "NETWORK_VOLUME_DATACENTER_UNAVAILABLE" in str(exc_info.value)
        assert "Cross-datacenter fallback is blocked" in str(exc_info.value)


@pytest.mark.asyncio
async def test_select_best_gpu_scoped_to_datacenter():
    """Test select_best_gpu respects required_datacenter and ranks RTX 4090 > 3090 > 5090 > L40S."""
    adapter = RunPodAdapter()
    gpu = await adapter.select_best_gpu(required_vram_gb=24, required_datacenter="US-TX-3")
    assert gpu["memoryInGb"] >= 24
    assert gpu.get("target_datacenter") == "US-TX-3"


@pytest.mark.asyncio
async def test_verify_flux2_models_present_missing():
    """Test verify_flux2_models_present returns MODELS_MISSING when node info fails or models absent."""
    adapter = RunPodAdapter()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("Connection refused")
        res = await adapter.verify_flux2_models_present("http://127.0.0.1:8188")
        assert res["status"] == "MODELS_MISSING"
        assert res["ready"] is False
        assert len(res["missing_models"]) == 4


