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

        # Verify features
        assert '/system/status' in html

    def test_root_endpoint_serves_pwa(self):
        """GET / should serve the PWA mobile client with Ollama & OpenAI parser support."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        html = resp.text
        assert 'data.message && typeof data.message === \'object\'' in html
        assert 'data.message.content' in html
        assert 'choices[0].message.content' in html

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


class TestResponseParserCompatibility:

    def test_ollama_message_object_support(self):
        """Verify that Ollama data.message object format is recognized in PWA client JS."""
        resp = client.get("/")
        html = resp.text
        assert 'data.message && typeof data.message === \'object\'' in html
        assert 'answerText = data.message.content;' in html

    def test_openai_choices_support(self):
        """Verify that OpenAI Chat Completions data.choices[0].message.content is recognized."""
        resp = client.get("/")
        html = resp.text
        assert 'data.choices && data.choices[0] && data.choices[0].message' in html
        assert 'answerText = data.choices[0].message.content;' in html

    def test_wrapper_result_object_support(self):
        """Verify that wrapper data.result object & string fields are supported."""
        resp = client.get("/")
        html = resp.text
        assert 'data.result && typeof data.result === \'object\'' in html

