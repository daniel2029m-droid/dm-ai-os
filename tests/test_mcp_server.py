import pytest
from fastapi.testclient import TestClient
from src.mcp.mcp_server import mcp_app

client = TestClient(mcp_app)

def test_mcp_tools_list():
    response = client.get("/mcp/tools")
    assert response.status_code == 200
    tools = response.json().get("tools", [])
    tool_names = [t["name"] for t in tools]
    assert "system_status" in tool_names
    assert "list_agents" in tool_names
    assert "run_agent" in tool_names
    assert "run_workflow" in tool_names
    assert "search_memory" in tool_names
    assert "get_artifacts" in tool_names

def test_mcp_call_system_status():
    response = client.post("/mcp/call", json={"tool": "system_status", "arguments": {}})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["result"]["status"] == "ONLINE"

def test_mcp_call_list_agents():
    response = client.post("/mcp/call", json={"tool": "list_agents", "arguments": {}})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert len(data["result"]) >= 6

def test_mcp_call_search_memory():
    response = client.post("/mcp/call", json={"tool": "search_memory", "arguments": {"query": "test"}})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert isinstance(data["result"], list)
