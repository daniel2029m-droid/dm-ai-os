import pytest
from fastapi.testclient import TestClient
from src.api.server import app

client = TestClient(app)

class TestMobileRemoteClientPWA:

    def test_connect_endpoint_serves_pwa(self):
        """GET /connect should serve the full touch-optimized iPhone PWA client."""
        resp = client.get("/connect")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        html = resp.text

        # Verify required strings for backward compatibility
        assert "DM AI OS" in html
        assert "Copiar Base URL" in html
        assert "ONLINE" in html
        assert "dm-secret-key-v1" in html

        # Verify iOS PWA Meta tags & Features
        assert 'name="apple-mobile-web-app-capable"' in html
        assert 'name="viewport"' in html
        assert 'viewport-fit=cover' in html
        assert 'manifest.json' in html

        # Verify Voice, Camera, File upload, Memory, and Agents components
        assert 'SpeechRecognition' in html
        assert 'speechSynthesis' in html
        assert 'cameraInput' in html
        assert 'fileInput' in html
        assert '/agent/run' in html
        assert '/workflow/run' in html
        assert '/memory/search' in html
        assert '/memory/store' in html
        assert '/system/status' in html

    def test_root_endpoint_serves_pwa(self):
        """GET / should also serve the PWA mobile client."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_manifest_endpoint(self):
        """GET /manifest.json should return valid PWA manifest JSON."""
        resp = client.get("/manifest.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "DM AI OS — iPhone Remote Terminal"
        assert data["display"] == "standalone"
        assert data["start_url"] == "/connect"

    def test_service_worker_endpoint(self):
        """GET /sw.js should return JavaScript service worker."""
        resp = client.get("/sw.js")
        assert resp.status_code == 200
        assert "application/javascript" in resp.headers.get("content-type", "")
        assert "addEventListener" in resp.text
