"""
DM AI OS v1.5.1 — Test Suite: Model Storage Plane
===================================================
Tests for:
  - Config loaders (model_registry.json, storage_nodes.json)
  - StorageNode abstraction
  - StorageVolume registration
  - Binary integrity validator
  - Model discovery across storage roots
  - Capability matrix evaluation
  - extra_model_paths.yaml generation
  - ModelStatus constants

Run from project root:
    cd C:/Users/moral/.gemini/antigravity-ide/scratch
    pip install -e . --quiet
    pytest tests/test_model_storage_plane.py -v
"""

import json
import os
import tempfile
import struct
from pathlib import Path

import pytest

# Ensure project root is in path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.model_storage_plane import (
    ModelStatus,
    StorageNode,
    StorageVolume,
    ModelStoragePlane,
    is_valid_safetensors_binary,
    load_model_catalog,
    load_storage_nodes,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_valid_safetensors(path: Path, size_bytes: int = 5_000_000) -> Path:
    """Creates a minimal valid safetensors file for testing."""
    header = json.dumps({"__metadata__": {"format": "pt"}}).encode("utf-8")
    header_len = struct.pack("<Q", len(header))  # 8-byte little-endian
    with open(path, "wb") as f:
        f.write(header_len)
        f.write(header)
        # Pad to desired size
        remaining = size_bytes - len(header_len) - len(header)
        if remaining > 0:
            f.write(b"\x00" * remaining)
    return path


# ── Test Group 1: ModelStatus Constants ───────────────────────────────────────

class TestModelStatus:
    def test_constants_exist(self):
        assert ModelStatus.NOT_REGISTERED == "NOT_REGISTERED"
        assert ModelStatus.CONFIGURED == "CONFIGURED"
        assert ModelStatus.DISCOVERED == "DISCOVERED"
        assert ModelStatus.VALIDATED == "VALIDATED"
        assert ModelStatus.READY == "READY"
        assert ModelStatus.MISSING_COMPONENTS == "MISSING_COMPONENTS"
        assert ModelStatus.INSUFFICIENT_VRAM == "INSUFFICIENT_VRAM"
        assert ModelStatus.STORAGE_UNAVAILABLE == "STORAGE_UNAVAILABLE"

    def test_ready_is_not_configured(self):
        # READY must be a distinct state from CONFIGURED
        assert ModelStatus.READY != ModelStatus.CONFIGURED


# ── Test Group 2: Config Loaders ──────────────────────────────────────────────

class TestConfigLoaders:
    def test_load_model_catalog_returns_dict(self):
        catalog = load_model_catalog()
        assert isinstance(catalog, dict)

    def test_catalog_has_sd15_base(self):
        catalog = load_model_catalog()
        assert "sd15_base" in catalog, "sd15_base must be in the registry"

    def test_catalog_has_flux_models_separate(self):
        """FLUX.1 and FLUX.2 Klein must be registered as separate model_ids."""
        catalog = load_model_catalog()
        # Both variants should exist independently
        assert "flux1_schnell_fp8" in catalog, "flux1_schnell_fp8 must be a separate model"
        assert "flux2_klein_4b_fp8" in catalog, "flux2_klein_4b_fp8 must be a separate model"
        # The old merged ID should NOT exist anymore
        assert "flux2_klein" not in catalog, "flux2_klein (old merged id) should not exist in v2 registry"

    def test_catalog_model_has_required_components(self):
        catalog = load_model_catalog()
        sd15 = catalog["sd15_base"]
        assert "required_components" in sd15
        assert len(sd15["required_components"]) >= 1

    def test_catalog_model_has_storage_node_ref(self):
        catalog = load_model_catalog()
        sd15 = catalog["sd15_base"]
        assert "storage" in sd15
        assert "storage_node" in sd15["storage"]

    def test_no_credentials_in_catalog(self):
        """Registry must not contain any email, password, or token."""
        catalog = load_model_catalog()
        catalog_str = json.dumps(catalog).lower()
        for forbidden in ["@gmail.com", "password", "token", "cookie", "refresh_token"]:
            assert forbidden not in catalog_str, f"Forbidden credential string '{forbidden}' found in catalog"

    def test_load_storage_nodes_returns_dict(self):
        nodes = load_storage_nodes()
        assert isinstance(nodes, dict)

    def test_no_credentials_in_storage_nodes(self):
        """storage_nodes.json must not contain any email or credentials."""
        nodes = load_storage_nodes()
        nodes_str = json.dumps(nodes).lower()
        for forbidden in ["@gmail.com", "password", "cookie", "refresh_token"]:
            assert forbidden not in nodes_str, f"Forbidden credential '{forbidden}' found in storage_nodes"

    def test_storage_nodes_have_required_keys(self):
        nodes = load_storage_nodes()
        for node_id, cfg in nodes.items():
            assert "provider" in cfg, f"Node '{node_id}' missing 'provider'"
            assert "mount_point" in cfg, f"Node '{node_id}' missing 'mount_point'"
            assert "root_path" in cfg, f"Node '{node_id}' missing 'root_path'"


# ── Test Group 3: StorageNode ─────────────────────────────────────────────────

class TestStorageNode:
    def test_resolve_full_path_default(self):
        node = StorageNode(
            node_id="test",
            provider="google_drive",
            display_name="Test",
            mount_point="/content/drive",
            root_path="MyDrive/DM-AI-OS-MODELS",
        )
        assert node.resolve_full_path() == Path("/content/drive/MyDrive/DM-AI-OS-MODELS")

    def test_resolve_full_path_env_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DM_DRIVE_MODELS_PATH", str(tmp_path))
        node = StorageNode(
            node_id="test",
            provider="google_drive",
            display_name="Test",
            mount_point="/content/drive",
            root_path="MyDrive/DM-AI-OS-MODELS",
            env_override="DM_DRIVE_MODELS_PATH",
        )
        assert node.resolve_full_path() == tmp_path

    def test_is_accessible_returns_false_when_path_missing(self):
        node = StorageNode(
            node_id="test",
            provider="google_drive",
            display_name="Test",
            mount_point="/nonexistent",
            root_path="path/that/does/not/exist",
        )
        assert node.is_accessible() is False

    def test_is_accessible_returns_true_when_path_exists(self, tmp_path):
        node = StorageNode(
            node_id="test",
            provider="local",
            display_name="Test",
            mount_point=str(tmp_path),
            root_path="",
        )
        assert node.is_accessible() is True


# ── Test Group 4: Binary Integrity Validator ──────────────────────────────────

class TestBinaryIntegrityValidator:
    def test_valid_safetensors_passes(self, tmp_path):
        f = _make_valid_safetensors(tmp_path / "model.safetensors", size_bytes=3_000_000)
        valid, reason = is_valid_safetensors_binary(f, min_bytes=0)
        assert valid, f"Expected valid, got: {reason}"

    def test_file_not_found_fails(self, tmp_path):
        valid, reason = is_valid_safetensors_binary(tmp_path / "missing.safetensors", min_bytes=0)
        assert not valid
        assert "not exist" in reason.lower()

    def test_empty_file_fails(self, tmp_path):
        f = tmp_path / "empty.safetensors"
        f.write_bytes(b"")
        valid, reason = is_valid_safetensors_binary(f, min_bytes=0)
        assert not valid

    def test_min_size_enforced(self, tmp_path):
        f = _make_valid_safetensors(tmp_path / "small.safetensors", size_bytes=1000)
        valid, reason = is_valid_safetensors_binary(f, min_bytes=5_000_000)
        assert not valid
        assert "below minimum" in reason.lower()

    def test_html_error_detected(self, tmp_path):
        f = tmp_path / "bad.safetensors"
        f.write_bytes(b"<html>404 Not Found</html>" + b"\x00" * 100)
        valid, reason = is_valid_safetensors_binary(f, min_bytes=0)
        assert not valid


# ── Test Group 5: ModelStoragePlane ───────────────────────────────────────────

class TestModelStoragePlane:
    def test_loads_catalog_from_registry_json(self):
        plane = ModelStoragePlane()
        assert "sd15_base" in plane.catalog
        assert len(plane.catalog) >= 4

    def test_register_storage_volume(self, tmp_path):
        plane = ModelStoragePlane()
        vol = plane.register_storage("test-vol", "local", tmp_path)
        assert "test-vol" in plane.storage_volumes
        assert vol.base_path == tmp_path

    def test_discover_model_file_found(self, tmp_path):
        plane = ModelStoragePlane()
        plane.register_storage("test-vol", "local", tmp_path)
        # Create a fake checkpoint file
        ckpt_dir = tmp_path / "checkpoints"
        ckpt_dir.mkdir()
        fake_file = ckpt_dir / "v1-5-pruned-emaonly-fp16.safetensors"
        fake_file.write_bytes(b"\x00" * 100)
        found = plane.discover_model_file("v1-5-pruned-emaonly-fp16.safetensors", "checkpoints")
        assert found is not None
        assert found == fake_file

    def test_discover_model_file_not_found(self, tmp_path):
        plane = ModelStoragePlane()
        plane.register_storage("test-vol", "local", tmp_path)
        found = plane.discover_model_file("nonexistent.safetensors", "checkpoints")
        assert found is None

    def test_resolve_model_not_registered(self):
        plane = ModelStoragePlane()
        result = plane.resolve_model("model_that_does_not_exist")
        assert result["status"] == ModelStatus.NOT_REGISTERED
        assert result["available"] is False

    def test_resolve_model_missing_components(self, tmp_path):
        """A model with no files in storage should report MISSING_COMPONENTS, not READY."""
        plane = ModelStoragePlane()
        plane.register_storage("test-vol", "local", tmp_path)
        result = plane.resolve_model("sd15_base")
        assert result["status"] == ModelStatus.MISSING_COMPONENTS
        assert result["available"] is False

    def test_generate_extra_model_paths_yaml(self, tmp_path):
        plane = ModelStoragePlane()
        plane.register_storage("test-vol", "local", tmp_path)
        yaml_content = plane.generate_extra_model_paths_yaml()
        assert "base_path:" in yaml_content
        assert str(tmp_path).replace("\\", "/") in yaml_content
        assert "checkpoints:" in yaml_content
        assert "diffusion_models:" in yaml_content
        assert "vae:" in yaml_content

    def test_evaluate_all_models_returns_dict(self):
        plane = ModelStoragePlane()
        result = plane.evaluate_all_models()
        assert isinstance(result, dict)
        # Every registered model should be evaluated
        for model_id in plane.catalog:
            assert model_id in result

    def test_get_storage_nodes_status(self):
        plane = ModelStoragePlane()
        status = plane.get_storage_nodes_status()
        assert "total" in status
        assert "accessible" in status
        assert "nodes" in status
        assert isinstance(status["nodes"], list)

    def test_reload_catalog(self):
        plane = ModelStoragePlane()
        count = plane.reload_catalog()
        assert count >= 4  # sd15_base, flux1_schnell_fp8, flux2_klein_4b_fp8, wan22_i2v...
