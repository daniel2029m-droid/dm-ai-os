import pytest
from fastapi.testclient import TestClient
from src.api.server import app

client = TestClient(app)
headers = {"X-API-Key": "dm-secret-key-v1"}


def test_v1_chat_completions_brain_pipeline():
    """Full pipeline test: Identity → Memory → ToolSelector → Ollama → Cache → MemoryWriter."""
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Hola, ¿cuáles son mis herramientas de automatización?"}]
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "dm-autonomous-brain"
    assert len(data["choices"]) > 0
    msg = data["choices"][0]["message"]
    assert msg["role"] == "assistant"
    assert len(msg["content"]) > 0
    # Verify BrainPipeline metadata is exposed
    assert "x_dm_metadata" in data
    meta = data["x_dm_metadata"]
    assert "memories_used" in meta
    assert "llm_model" in meta
    assert "execution_time_sec" in meta
    assert meta["source"] in ("live", "cache")


def test_v1_chat_completions_cache_hit():
    """Second identical request should return from cache (source='cache')."""
    payload = {
        "model": "dm-autonomous-brain",
        "messages": [{"role": "user", "content": "Prueba de cache: automatizacion de n8n"}]
    }
    r1 = client.post("/v1/chat/completions", json=payload)
    r2 = client.post("/v1/chat/completions", json=payload)
    assert r2.status_code == 200
    assert r2.json()["x_dm_metadata"]["source"] == "cache"


def test_v1_chat_completions_agent_routing():
    """Prompt containing keyword 'busca' should trigger research agent routing."""
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "busca información sobre inteligencia artificial"}]
        }
    )
    assert response.status_code == 200
    meta = response.json()["x_dm_metadata"]
    assert meta["agent_used"] == "research"


def test_v1_models_list():
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    ids = [m["id"] for m in data["data"]]
    assert "dm-autonomous-brain" in ids
