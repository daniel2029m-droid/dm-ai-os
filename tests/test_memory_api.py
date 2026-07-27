import pytest
from fastapi.testclient import TestClient
from src.api.server import app

client = TestClient(app)
headers = {"X-API-Key": "dm-secret-key-v1"}

def test_memory_profile_api():
    response = client.get("/memory/profile", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "Daniel" in data["name"]  # Acepta 'Daniel' o 'Daniel Morales'

def test_memory_store_search_forget_api():
    # Store
    store_resp = client.post(
        "/memory/store",
        headers=headers,
        json={"content": "El usuario utiliza n8n y Python para automatizaciones.", "category": "tools"}
    )
    assert store_resp.status_code == 200
    mem_id = store_resp.json()["memory_id"]

    # Search
    search_resp = client.post(
        "/memory/search",
        headers=headers,
        json={"query": "n8n", "category": "tools"}
    )
    assert search_resp.status_code == 200
    assert len(search_resp.json()) > 0

    # Forget
    forget_resp = client.post(
        "/memory/forget",
        headers=headers,
        json={"memory_id": mem_id}
    )
    assert forget_resp.status_code == 200
    assert forget_resp.json()["status"] == "SUCCESS"

def test_memory_context_api():
    response = client.get("/memory/context?query=automation", headers=headers)
    assert response.status_code == 200
    assert "context" in response.json()
