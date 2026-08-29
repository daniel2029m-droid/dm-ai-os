"""
Test Suite Phase 15.6 — Secure Remote Asset Streaming & HMAC-SHA256 Presigned URLs.
Validates zero master API Key exposure, cryptographic single-asset binding, expiration,
anti-traversal security, and inline/attachment media streaming.
"""
import os
import sys
import time
import hmac
import hashlib
import tempfile
from pathlib import Path

# Ensure scratch root directory is in sys.path
ROOT_DIR = Path(__file__).parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.storage.storage_layer import storage
from src.api.creative_assets_router import generate_signed_urls

client = TestClient(app)

TEST_SECRET = "test-secret-key-super-secure-dm-ai-os-2026"
TEST_API_KEY = "dm-test-api-key"

@pytest.fixture(autouse=True)
def setup_env_and_cleanup(monkeypatch):
    """Sets up signing secret, API key, and test environment for every test."""
    monkeypatch.setenv("DM_MEDIA_SIGNING_SECRET", TEST_SECRET)
    monkeypatch.setenv("DM_API_KEY", TEST_API_KEY)
    monkeypatch.setenv("DM_MEDIA_URL_TTL_SEC", "1800")
    yield


@pytest.fixture
def sample_vaulted_job():
    """Creates a mock vaulted creative job in SQLite JobStore with physical asset file."""
    job_id = "test-job-e2e-vault-001"
    
    # 1. Create media directory structure in Project_State
    media_dir = Path("Project_State") / "Artifacts" / "media" / job_id
    media_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. Write physical test PNG file
    png_file = media_dir / "sample_render.png"
    test_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    png_file.write_bytes(test_content)
    test_sha256 = hashlib.sha256(test_content).hexdigest()
    
    # 3. Insert record in JobStore SQLite
    rel_asset_path = str(Path("Artifacts") / "media" / job_id / "sample_render.png")
    storage.job_store.create_job({
        "job_id": job_id,
        "workflow_name": "sd15_txt2img",
        "prompt": "A majestic eagle over snowy mountains",
        "model_checkpoint": "v1-5-pruned-emaonly-fp16.safetensors",
        "status": "COMPLETED",
        "output_assets": [rel_asset_path],
        "output_sha256": test_sha256,
        "output_size_bytes": len(test_content)
    })
    
    yield {
        "job_id": job_id,
        "file_path": png_file,
        "content": test_content,
        "sha256": test_sha256,
        "rel_path": rel_asset_path
    }
    
    # Cleanup physical file
    if png_file.exists():
        png_file.unlink()
    if media_dir.exists():
        try:
            media_dir.rmdir()
        except OSError:
            pass


# ─── Tests ───────────────────────────────────────────────────────────────────

def test_a_valid_signature_returns_200_inline(sample_vaulted_job):
    """A. Valid signature returns HTTP 200 with exact binary content and inline header."""
    job_id = sample_vaulted_job["job_id"]
    signed = generate_signed_urls(job_id=job_id)
    
    res = client.get(signed["view_url"])
    assert res.status_code == 200
    assert res.content == sample_vaulted_job["content"]
    assert "image/png" in res.headers.get("content-type", "")
    assert "inline" in res.headers.get("content-disposition", "")
    assert "sample_render.png" in res.headers.get("content-disposition", "")


def test_b_expired_signature_returns_403(sample_vaulted_job):
    """B. Expired signature (exp < now) returns HTTP 403 Forbidden."""
    job_id = sample_vaulted_job["job_id"]
    past_exp = int(time.time()) - 60  # Expired 60s ago
    payload = f"{job_id}:{past_exp}:view".encode("utf-8")
    sig = hmac.new(TEST_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    
    url = f"/api/v1/creative/assets/{job_id}/view?exp={past_exp}&sig={sig}"
    res = client.get(url)
    assert res.status_code == 403
    assert "expired" in res.json().get("detail", "").lower()


def test_c_tampered_signature_returns_403(sample_vaulted_job):
    """C. Tampered signature returns HTTP 403 Forbidden."""
    job_id = sample_vaulted_job["job_id"]
    signed = generate_signed_urls(job_id=job_id)
    
    # Tamper with signature
    tampered_url = signed["view_url"][:-4] + "ffff"
    res = client.get(tampered_url)
    assert res.status_code == 403
    assert "invalid signature" in res.json().get("detail", "").lower()


def test_d_mismatched_job_id_with_other_signature_returns_403(sample_vaulted_job):
    """D. Changing job_id while reusing signature from another job returns HTTP 403."""
    job_id = sample_vaulted_job["job_id"]
    signed = generate_signed_urls(job_id=job_id)
    
    # Replace job_id in URL with another job id
    other_url = signed["view_url"].replace(job_id, "other-unauthorized-job-id")
    res = client.get(other_url)
    assert res.status_code == 403
    assert "invalid signature" in res.json().get("detail", "").lower()


def test_e_mismatched_action_view_vs_download_returns_403(sample_vaulted_job):
    """E. Using signature generated for 'view' on the '/download' endpoint returns HTTP 403."""
    job_id = sample_vaulted_job["job_id"]
    signed = generate_signed_urls(job_id=job_id)
    
    # Replace /view with /download without changing signature
    swapped_url = signed["view_url"].replace("/view?", "/download?")
    res = client.get(swapped_url)
    assert res.status_code == 403
    assert "invalid signature" in res.json().get("detail", "").lower()


def test_f_nonexistent_job_returns_404():
    """F. Non-existent job in JobStore returns HTTP 404 Not Found."""
    fake_job_id = "non-existent-uuid-999"
    exp = int(time.time()) + 1800
    payload = f"{fake_job_id}:{exp}:view".encode("utf-8")
    sig = hmac.new(TEST_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    
    url = f"/api/v1/creative/assets/{fake_job_id}/view?exp={exp}&sig={sig}"
    res = client.get(url)
    assert res.status_code == 404
    assert "not found" in res.json().get("detail", "").lower()


def test_g_non_completed_job_returns_400():
    """G. Incomplete job in JobStore (RUNNING/SUBMITTED) returns HTTP 400 Bad Request."""
    job_id = "job-still-running-002"
    storage.job_store.create_job({
        "job_id": job_id,
        "workflow_name": "sd15",
        "prompt": "test",
        "status": "SUBMITTED"
    })
    
    exp = int(time.time()) + 1800
    payload = f"{job_id}:{exp}:view".encode("utf-8")
    sig = hmac.new(TEST_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    
    url = f"/api/v1/creative/assets/{job_id}/view?exp={exp}&sig={sig}"
    res = client.get(url)
    assert res.status_code == 400
    assert "not completed" in res.json().get("detail", "").lower()


def test_h_missing_physical_file_returns_404(sample_vaulted_job):
    """H. Missing physical file on disk returns HTTP 404 Not Found."""
    job_id = sample_vaulted_job["job_id"]
    # Delete physical file
    sample_vaulted_job["file_path"].unlink()
    
    signed = generate_signed_urls(job_id=job_id)
    res = client.get(signed["view_url"])
    assert res.status_code == 404
    assert "not found on disk" in res.json().get("detail", "").lower()


def test_i_path_traversal_attempt_returns_403():
    """I. Path traversal attempt in JobStore output_assets returns HTTP 403 Forbidden."""
    job_id = "job-malicious-traversal-003"
    storage.job_store.create_job({
        "job_id": job_id,
        "workflow_name": "sd15",
        "prompt": "test",
        "status": "COMPLETED",
        "output_assets": ["../../../../Windows/win.ini"],
        "output_sha256": "fakehash"
    })
    
    exp = int(time.time()) + 1800
    payload = f"{job_id}:{exp}:view".encode("utf-8")
    sig = hmac.new(TEST_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    
    url = f"/api/v1/creative/assets/{job_id}/view?exp={exp}&sig={sig}"
    res = client.get(url)
    assert res.status_code == 403
    assert "outside the media vault" in res.json().get("detail", "").lower()


def test_j_download_endpoint_returns_attachment_header(sample_vaulted_job):
    """J & M. Download endpoint returns attachment Content-Disposition header."""
    job_id = sample_vaulted_job["job_id"]
    signed = generate_signed_urls(job_id=job_id)
    
    res = client.get(signed["download_url"])
    assert res.status_code == 200
    assert res.content == sample_vaulted_job["content"]
    assert "attachment" in res.headers.get("content-disposition", "")
    assert "sample_render.png" in res.headers.get("content-disposition", "")


def test_k_metadata_endpoint_authenticated(sample_vaulted_job, monkeypatch):
    """K. Metadata endpoint requires API Key when require_auth is enabled and returns complete metadata & signed URLs."""
    monkeypatch.setattr("src.api.auth.load_security_config", lambda: {"require_auth": True})
    job_id = sample_vaulted_job["job_id"]
    
    # 1. Without auth -> 403
    unauth_res = client.get(f"/api/v1/creative/assets/{job_id}/metadata")
    assert unauth_res.status_code == 403
    
    # 2. With auth -> 200 + metadata
    auth_res = client.get(
        f"/api/v1/creative/assets/{job_id}/metadata",
        headers={"X-API-Key": TEST_API_KEY}
    )
    assert auth_res.status_code == 200
    data = auth_res.json()
    assert data["status"] == "SUCCESS"
    assert data["job_id"] == job_id
    assert data["sha256"] == sample_vaulted_job["sha256"]
    assert "urls" in data
    assert "view_url" in data["urls"]
    assert "download_url" in data["urls"]


def test_l_sign_endpoint_authenticated(sample_vaulted_job, monkeypatch):
    """L. Sign endpoint requires API Key when require_auth is enabled and generates fresh presigned URLs."""
    monkeypatch.setattr("src.api.auth.load_security_config", lambda: {"require_auth": True})
    job_id = sample_vaulted_job["job_id"]
    
    # 1. Without auth -> 403
    unauth_res = client.post(f"/api/v1/creative/assets/{job_id}/sign")
    assert unauth_res.status_code == 403
    
    # 2. With auth -> 200
    res = client.post(
        f"/api/v1/creative/assets/{job_id}/sign",
        headers={"X-API-Key": TEST_API_KEY}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "view_url" in data
    assert "download_url" in data
    assert data["ttl_seconds"] == 1800


def test_p_missing_secret_fails_safe_500(sample_vaulted_job, monkeypatch):
    """P. When DM_MEDIA_SIGNING_SECRET is missing, server fails safe with HTTP 500 without hardcoded fallbacks."""
    monkeypatch.delenv("DM_MEDIA_SIGNING_SECRET", raising=False)
    job_id = sample_vaulted_job["job_id"]
    
    res = client.get(f"/api/v1/creative/assets/{job_id}/view?exp=1800000000&sig=abc")
    assert res.status_code == 500
    assert "not configured" in res.json().get("detail", "").lower()
