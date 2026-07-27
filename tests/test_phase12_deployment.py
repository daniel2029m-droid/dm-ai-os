import pytest
import os
import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from src.api.server import app

@pytest.fixture(scope="module")
def client():
    return TestClient(app)

# Provide a mock URL for asset generation testing
TEST_TUNNEL_URL = "https://test-tunnel.trycloudflare.com"

class TestDeploymentEndpoints:

    def test_connect_endpoint_exists(self, client):
        """GET /connect should return a 200 HTML response."""
        resp = client.get("/connect")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_connect_endpoint_content(self, client):
        """GET /connect should contain required UI elements."""
        resp = client.get("/connect")
        html = resp.text
        assert "DM AI OS" in html
        assert "Copiar Base URL" in html
        assert "ONLINE" in html
        assert "dm-secret-key-v1" in html

class TestAssetGenerator:

    @pytest.fixture(autouse=True)
    def run_generator(self):
        """Run the generator script before checking assets."""
        script_path = Path("scripts/generate_deployment_assets.py")
        if not script_path.exists():
            pytest.skip("Asset generator script not found")
            
        import sys
        result = subprocess.run(
            [sys.executable, str(script_path), "--url", TEST_TUNNEL_URL],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Generator failed: {result.stderr}"
        yield

    def test_json_config_created(self):
        """Verify openai_connection.json is generated correctly."""
        json_path = Path("deployment/openai_connection.json")
        assert json_path.exists()
        
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        assert data["name"] == "DM AI OS"
        assert data["base_url"] == f"{TEST_TUNNEL_URL}/v1"
        assert data["api_key"] == "dm-secret-key-v1"
        assert data["model"] == "dm-autonomous-brain"

    def test_web_qr_created(self):
        """Verify the web URL QR code is generated."""
        qr_path = Path("deployment/dm_ai_os_qr.png")
        assert qr_path.exists()
        assert qr_path.stat().st_size > 0

    def test_config_qr_created(self):
        """Verify the JSON config QR code is generated."""
        qr_path = Path("deployment/openai_config_qr.png")
        assert qr_path.exists()
        assert qr_path.stat().st_size > 0
