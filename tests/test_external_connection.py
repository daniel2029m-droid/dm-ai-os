import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def test_providers_config():
    p_path = BASE_DIR / "config" / "providers.json"
    assert p_path.exists()
    with open(p_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["ollama"]["enabled"] is True
    assert data["openai"]["enabled"] is False
    assert data["anthropic"]["enabled"] is False

def test_security_config():
    s_path = BASE_DIR / "config" / "security.json"
    assert s_path.exists()
    with open(s_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "require_auth" in data
    assert "allow_external_clients" in data

def test_connections_registry():
    c_path = BASE_DIR / "Project_State" / "Connections" / "connections.json"
    assert c_path.exists()
    with open(c_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["active_connections"]) > 0

def test_mcp_registry_json():
    m_path = BASE_DIR / "Project_State" / "Connections" / "mcp_registry.json"
    assert m_path.exists()
    with open(m_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["mcp_server"]["port"] == 8001
