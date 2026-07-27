import pytest
from fastapi.testclient import TestClient
from src.mcp.mcp_server import mcp_app

client = TestClient(mcp_app)

def test_mcp_get_user_profile():
    response = client.post("/mcp/call", json={"tool": "get_user_profile", "arguments": {"user_id": "daniel"}})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "Daniel" in data["result"]["name"]  # Acepta 'Daniel' o 'Daniel Morales'

def test_mcp_remember_and_get_context():
    rem_resp = client.post("/mcp/call", json={
        "tool": "remember",
        "arguments": {"content": "El usuario prefiere la arquitectura Multi-Agent basada en eventos."}
    })
    assert rem_resp.status_code == 200
    assert rem_resp.json()["status"] == "SUCCESS"

    ctx_resp = client.post("/mcp/call", json={
        "tool": "get_context",
        "arguments": {"query": "arquitectura"}
    })
    assert ctx_resp.status_code == 200
    assert "User Profile" in ctx_resp.json()["result"]
