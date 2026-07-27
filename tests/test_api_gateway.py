import pytest
import asyncio
from fastapi.testclient import TestClient
from src.api.server import app

client = TestClient(app)
headers = {"X-API-Key": "dm-secret-key-v1"}

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ONLINE"
    assert data["version"] == "v1.0.0-production"

def test_system_status_endpoint():
    response = client.get("/system/status", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["system_status"] == "ONLINE"
    assert len(data["agents"]) >= 6

def test_list_agents_endpoint():
    response = client.get("/agents", headers=headers)
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) >= 6
    agent_names = [a["name"] for a in agents]
    assert "browser" in agent_names
    assert "computer" in agent_names

def test_agent_run_endpoint():
    response = client.post(
        "/agent/run",
        headers=headers,
        json={"agent": "computer", "task": "sys_info", "params": {"action": "sys_info"}}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["agent"] == "computer"

def test_workflow_run_endpoint():
    response = client.post(
        "/workflow/run",
        headers=headers,
        json={"goal": "API Gateway Integration Test"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "research" in data["result"]

def test_v1_chat_completions_endpoint():
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Hola, prueba de integración Grok Build"}]
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "dm-autonomous-brain"
    assert len(data["choices"]) > 0
    assert "message" in data["choices"][0]

