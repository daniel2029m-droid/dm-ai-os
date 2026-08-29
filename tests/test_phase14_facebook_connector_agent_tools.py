"""
Tests for FacebookConnector and AgentTools (Fase 14.2/14.3)
"""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# FacebookConnector tests (mocked Playwright)
# ---------------------------------------------------------------------------

class TestFacebookConnectorOffline:
    """Tests that run without a real browser — mock Playwright."""

    def test_import(self):
        """Module must be importable even without playwright installed."""
        from src.specialists.facebook_connector import FacebookConnector, _SESSIONS_ROOT
        assert FacebookConnector is not None
        assert _SESSIONS_ROOT is not None

    def test_safe_path_construction(self):
        from src.specialists.facebook_connector import _SESSIONS_ROOT
        p = _SESSIONS_ROOT / "facebook_daniel" / "cookies.json"
        assert "facebook_daniel" in str(p)

    def test_no_playwright_raises_on_init(self, monkeypatch):
        """When playwright is not installed, __init__ should raise immediately."""
        monkeypatch.setattr(
            "src.specialists.facebook_connector.PLAYWRIGHT_AVAILABLE", False
        )
        from src.specialists.facebook_connector import FacebookConnector, FacebookConnectorError
        with pytest.raises(FacebookConnectorError, match="playwright is not installed"):
            FacebookConnector(user_id="test")


# ---------------------------------------------------------------------------
# AgentTools tests (no LLM required)
# ---------------------------------------------------------------------------

class TestAgentTools:

    def test_tool_write_and_read_file(self, tmp_path, monkeypatch):
        """write_file creates a file; read_file returns its content."""
        import src.core.agent_tools as at
        monkeypatch.setattr(at, "_WORKSPACE_ROOT", tmp_path)

        result = at.tool_write_file("test_dir/hello.py", "print('hello')")
        assert result["ok"] is True
        assert (tmp_path / "test_dir" / "hello.py").exists()

        read_result = at.tool_read_file("test_dir/hello.py")
        assert read_result["ok"] is True
        assert "print('hello')" in read_result["content"]

    def test_tool_write_file_outside_workspace_blocked(self, tmp_path, monkeypatch):
        """Directory traversal should be blocked."""
        import src.core.agent_tools as at
        monkeypatch.setattr(at, "_WORKSPACE_ROOT", tmp_path)

        result = at.tool_write_file("../../etc/passwd", "evil")
        assert result["ok"] is False
        assert "outside workspace" in result["error"]

    def test_tool_list_dir(self, tmp_path, monkeypatch):
        """list_dir returns the correct entries."""
        import src.core.agent_tools as at
        monkeypatch.setattr(at, "_WORKSPACE_ROOT", tmp_path)

        (tmp_path / "src").mkdir()
        (tmp_path / "README.md").write_text("hi")

        result = at.tool_list_dir(".")
        assert result["ok"] is True
        names = [e["name"] for e in result["entries"]]
        assert "src" in names
        assert "README.md" in names

    def test_tool_read_file_not_found(self, tmp_path, monkeypatch):
        import src.core.agent_tools as at
        monkeypatch.setattr(at, "_WORKSPACE_ROOT", tmp_path)

        result = at.tool_read_file("nonexistent.py")
        assert result["ok"] is False
        assert "not found" in result["error"]

    def test_tool_run_command_allowed(self, tmp_path, monkeypatch):
        """python --version should succeed."""
        import src.core.agent_tools as at
        monkeypatch.setattr(at, "_WORKSPACE_ROOT", tmp_path)

        result = at.tool_run_command("python --version", cwd=".")
        # returncode 0 OR stdout contains "Python"
        assert result["ok"] or "Python" in result.get("stdout", "") + result.get("stderr", "")

    def test_tool_run_command_blocked(self, tmp_path, monkeypatch):
        """rm -rf should be blocked."""
        import src.core.agent_tools as at
        monkeypatch.setattr(at, "_WORKSPACE_ROOT", tmp_path)

        result = at.tool_run_command("rm -rf /")
        assert result["ok"] is False
        assert "not in the allowed list" in result["error"]

    def test_tool_search_file(self, tmp_path, monkeypatch):
        """search_file returns correct matching lines."""
        import src.core.agent_tools as at
        monkeypatch.setattr(at, "_WORKSPACE_ROOT", tmp_path)

        (tmp_path / "code.py").write_text("class Foo:\n    def bar(self):\n        pass\n")
        result = at.tool_search_file("code.py", "class")
        assert result["ok"] is True
        assert len(result["matches"]) == 1
        assert result["matches"][0]["line"] == 1

    def test_dispatch_tool(self, tmp_path, monkeypatch):
        """dispatch_tool routes to the correct function."""
        import src.core.agent_tools as at
        monkeypatch.setattr(at, "_WORKSPACE_ROOT", tmp_path)

        raw = at.dispatch_tool("write_file", {"path": "x.txt", "content": "hello"})
        parsed = json.loads(raw)
        assert parsed["ok"] is True

    def test_dispatch_unknown_tool(self):
        import src.core.agent_tools as at
        raw = at.dispatch_tool("launch_missile", {})
        parsed = json.loads(raw)
        assert parsed["ok"] is False
        assert "Unknown tool" in parsed["error"]

    @pytest.mark.asyncio
    async def test_run_agentic_loop_no_tool_calls(self, monkeypatch):
        """When Ollama returns a plain text response (no tool_calls), loop exits immediately."""
        import src.core.agent_tools as at

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "Here is the code you asked for.",
                "tool_calls": [],
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("src.core.agent_tools.httpx.AsyncClient", return_value=mock_client):
            result = await at.run_agentic_loop("Write a hello world script")

        assert "code" in result.lower() or "here" in result.lower()

    @pytest.mark.asyncio
    async def test_run_agentic_loop_single_tool_call(self, tmp_path, monkeypatch):
        """Loop executes write_file tool call, then returns final answer."""
        import src.core.agent_tools as at
        monkeypatch.setattr(at, "_WORKSPACE_ROOT", tmp_path)

        # First response: tool call to write_file
        resp1 = MagicMock()
        resp1.raise_for_status = MagicMock()
        resp1.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "function": {
                        "name": "write_file",
                        "arguments": {"path": "hello.py", "content": "print('hi')"},
                    }
                }],
            }
        }

        # Second response: final text answer
        resp2 = MagicMock()
        resp2.raise_for_status = MagicMock()
        resp2.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "Done! I created hello.py.",
                "tool_calls": [],
            }
        }

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=[resp1, resp2])

        with patch("src.core.agent_tools.httpx.AsyncClient", return_value=mock_client):
            result = await at.run_agentic_loop("Create hello.py")

        assert "Done" in result
        assert (tmp_path / "hello.py").exists()
        assert "print('hi')" in (tmp_path / "hello.py").read_text()
