"""
Phase 9 — OpenAI Compatibility Layer Test Suite
================================================
Tests:
  - GET /v1/models (format, content, deduplication)
  - POST /v1/chat/completions (non-streaming)
  - POST /v1/chat/completions (streaming SSE)
  - POST /v1/chat/completions (tool calls)
  - POST /v1/chat/completions (all parameters, unknown params ignored)
  - POST /v1/responses (Responses API)
  - Auth modes (bearer, api_key, no-auth)
  - Memory pipeline integration
  - Identity pipeline integration
  - Cache pipeline integration
  - MCP tool registry (dynamic)
  - Tool translator (OpenAI → MCP)
  - Debug trace system
  - Grok Build compatibility
  - Open WebUI compatibility
  - Cursor compatibility
  - Cherry Studio compatibility
  - LibreChat compatibility
  - Regression: all previous platform routes

Run with:
    pytest tests/test_phase9_openai_compat.py -v --tb=short
"""

import json
import sys
import os
import time
import uuid
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure src is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from httpx import AsyncClient

# ─────────────────────────────────────────────────────────────────────────────
# App fixture — import the real app
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app():
    """Import and return the FastAPI app."""
    from src.api.server import app as fastapi_app
    return fastapi_app


@pytest.fixture(scope="module")
def client(app):
    """Synchronous test client."""
    return TestClient(app, raise_server_exceptions=True)


# ─────────────────────────────────────────────────────────────────────────────
# Mock BrainPipeline to avoid requiring live Ollama
# ─────────────────────────────────────────────────────────────────────────────

MOCK_BRAIN_RESULT = {
    "answer": "This is a test response from the DM AI Operating System BrainPipeline.",
    "user_id": "test_user",
    "profile_name": "Test User",
    "memories_used": 2,
    "agent_used": None,
    "llm_model": "qwen2.5:1.5b",
    "execution_time_sec": 0.42,
    "source": "live",
}

MOCK_BRAIN_RESULT_WITH_AGENT = {
    **MOCK_BRAIN_RESULT,
    "agent_used": "research",
    "answer": "Research completed. Here are the findings on quantum computing...",
}


@pytest.fixture(autouse=True)
def mock_brain_pipeline():
    """Mock BrainPipeline.process so tests don't require Ollama."""
    with patch(
        "src.api.brain_pipeline.BrainPipeline.process",
        new_callable=AsyncMock,
        return_value=MOCK_BRAIN_RESULT,
    ) as mock:
        yield mock


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: GET /v1/models
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

class TestModels:

    def test_models_endpoint_exists(self, client):
        """GET /v1/models returns 200."""
        resp = client.get("/v1/models")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    def test_models_response_format(self, client):
        """Response has OpenAI list format."""
        resp = client.get("/v1/models")
        data = resp.json()
        assert data["object"] == "list"
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

    def test_models_has_dm_models(self, client):
        """All 8 DM virtual models are present."""
        resp = client.get("/v1/models")
        ids = {m["id"] for m in resp.json()["data"]}
        expected = {
            "dm-autonomous-brain", "dm-reasoner", "dm-fast", "dm-memory",
            "dm-browser", "dm-research", "dm-media", "dm-facebook",
        }
        missing = expected - ids
        assert not missing, f"Missing models: {missing}"

    def test_models_each_has_required_fields(self, client):
        """Each model object has id, object, created, owned_by."""
        resp = client.get("/v1/models")
        for m in resp.json()["data"]:
            assert "id" in m, f"Model missing 'id': {m}"
            assert "object" in m, f"Model missing 'object': {m}"
            assert "created" in m, f"Model missing 'created': {m}"
            assert "owned_by" in m, f"Model missing 'owned_by': {m}"
            assert m["object"] == "model"

    def test_models_no_duplicates(self, client):
        """No duplicate model IDs."""
        resp = client.get("/v1/models")
        ids = [m["id"] for m in resp.json()["data"]]
        assert len(ids) == len(set(ids)), f"Duplicate model IDs found: {ids}"

    def test_models_dm_autonomous_brain_owned_by_dm(self, client):
        """DM virtual models have owned_by dm-platform."""
        resp = client.get("/v1/models")
        dm_models = [m for m in resp.json()["data"] if m["id"].startswith("dm-")]
        for m in dm_models:
            assert m["owned_by"] == "dm-platform", f"Model {m['id']} wrong owner"


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: POST /v1/chat/completions — Non-streaming
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

class TestChatCompletionsNonStreaming:

    def _basic_request(self) -> dict:
        return {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Hello, test message"}],
        }

    def test_endpoint_exists(self, client):
        """POST /v1/chat/completions returns 200."""
        resp = client.post("/v1/chat/completions", json=self._basic_request())
        assert resp.status_code == 200

    def test_response_has_openai_format(self, client):
        """Response matches OpenAI chat.completion format."""
        resp = client.post("/v1/chat/completions", json=self._basic_request())
        data = resp.json()
        assert data["object"] == "chat.completion"
        assert "id" in data
        assert data["id"].startswith("chatcmpl-")
        assert "created" in data
        assert "model" in data
        assert "choices" in data
        assert len(data["choices"]) >= 1

    def test_choice_structure(self, client):
        """Each choice has index, message, finish_reason."""
        resp = client.post("/v1/chat/completions", json=self._basic_request())
        choice = resp.json()["choices"][0]
        assert "index" in choice
        assert "message" in choice
        assert "finish_reason" in choice
        assert choice["message"]["role"] == "assistant"
        assert isinstance(choice["message"]["content"], str)

    def test_usage_tokens(self, client):
        """Response includes usage token counts."""
        resp = client.post("/v1/chat/completions", json=self._basic_request())
        data = resp.json()
        assert "usage" in data
        usage = data["usage"]
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert "total_tokens" in usage
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]

    def test_answer_is_from_brain_pipeline(self, client, mock_brain_pipeline):
        """Response content comes from BrainPipeline."""
        resp = client.post("/v1/chat/completions", json=self._basic_request())
        content = resp.json()["choices"][0]["message"]["content"]
        assert MOCK_BRAIN_RESULT["answer"] in content

    def test_system_message_supported(self, client):
        """System + user messages both accepted."""
        req = {
            "model": "dm-autonomous-brain",
            "messages": [
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": "Test question"},
            ],
        }
        resp = client.post("/v1/chat/completions", json=req)
        assert resp.status_code == 200

    def test_all_openai_params_accepted(self, client):
        """All documented OpenAI parameters accepted without error."""
        req = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Test"}],
            "temperature": 0.7,
            "top_p": 0.9,
            "n": 1,
            "stream": False,
            "stop": ["\n"],
            "max_tokens": 500,
            "presence_penalty": 0.1,
            "frequency_penalty": 0.1,
            "seed": 42,
            "response_format": {"type": "text"},
            "user": "test_user",
            "metadata": {"session_id": "abc"},
            "store": True,
            "reasoning": {"effort": "high"},
        }
        resp = client.post("/v1/chat/completions", json=req)
        assert resp.status_code == 200

    def test_unknown_params_ignored(self, client):
        """Unknown parameters silently ignored (no 422 error)."""
        req = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Test"}],
            "future_openai_param": "some_value",
            "grok_build_extension": {"key": "value"},
            "completely_unknown_field": 12345,
        }
        resp = client.post("/v1/chat/completions", json=req)
        # Must not return 422 or 400
        assert resp.status_code == 200, f"Unknown params caused error: {resp.json()}"

    def test_user_field_sets_identity(self, client, mock_brain_pipeline):
        """The 'user' field is passed to BrainPipeline as user_id."""
        req = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Test"}],
            "user": "specific_user_123",
        }
        client.post("/v1/chat/completions", json=req)
        call_kwargs = mock_brain_pipeline.call_args
        assert call_kwargs is not None
        # user_id should be passed through
        kwargs = call_kwargs.kwargs
        assert kwargs.get("user_id") == "specific_user_123"

    def test_n_completions(self, client):
        """n=2 returns 2 choices."""
        req = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Test n=2"}],
            "n": 2,
        }
        resp = client.post("/v1/chat/completions", json=req)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["choices"]) == 2

    def test_model_field_echoed(self, client):
        """Response echoes the requested model name."""
        req = {
            "model": "dm-research",
            "messages": [{"role": "user", "content": "Test"}],
        }
        resp = client.post("/v1/chat/completions", json=req)
        assert resp.json()["model"] == "dm-research"

    def test_finish_reason_stop(self, client):
        """Non-tool response has finish_reason=stop."""
        resp = client.post("/v1/chat/completions", json=self._basic_request())
        assert resp.json()["choices"][0]["finish_reason"] == "stop"

    def test_id_is_unique_per_request(self, client):
        """Each request gets a unique ID."""
        r1 = client.post("/v1/chat/completions", json=self._basic_request()).json()
        r2 = client.post("/v1/chat/completions", json=self._basic_request()).json()
        assert r1["id"] != r2["id"]

    def test_empty_messages_returns_error(self, client):
        """Empty messages list returns 422."""
        req = {"model": "dm-autonomous-brain", "messages": []}
        resp = client.post("/v1/chat/completions", json=req)
        assert resp.status_code in (400, 422)

    def test_invalid_json_returns_error(self, client):
        """Invalid JSON returns 400."""
        resp = client.post(
            "/v1/chat/completions",
            content=b"not json {{{",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code in (400, 422)


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Streaming SSE
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

class TestStreaming:

    def test_streaming_returns_200(self, client):
        """stream=True returns 200 with text/event-stream content type."""
        req = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Stream test"}],
            "stream": True,
        }
        with client.stream("POST", "/v1/chat/completions", json=req) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_streaming_contains_done(self, client):
        """Stream ends with data: [DONE]."""
        req = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Stream test DONE check"}],
            "stream": True,
        }
        with client.stream("POST", "/v1/chat/completions", json=req) as resp:
            raw = resp.read().decode()
        assert "data: [DONE]" in raw, f"[DONE] not found in stream:\n{raw[:500]}"

    def test_streaming_chunks_are_valid_sse(self, client):
        """Each non-DONE line starts with 'data: ' and contains valid JSON."""
        req = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Parse SSE chunks"}],
            "stream": True,
        }
        with client.stream("POST", "/v1/chat/completions", json=req) as resp:
            raw = resp.read().decode()

        data_lines = [
            line[6:] for line in raw.split("\n")
            if line.startswith("data: ") and line.strip() != "data: [DONE]"
        ]
        assert len(data_lines) > 0, "No data: lines found in stream"

        for line in data_lines:
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                pytest.fail(f"Invalid JSON in SSE chunk: {line}")
            assert "id" in chunk
            assert "object" in chunk
            assert chunk["object"] == "chat.completion.chunk"
            assert "choices" in chunk
            assert isinstance(chunk["choices"], list)

    def test_streaming_first_chunk_has_role(self, client):
        """First SSE chunk contains role=assistant delta."""
        req = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Role check"}],
            "stream": True,
        }
        with client.stream("POST", "/v1/chat/completions", json=req) as resp:
            raw = resp.read().decode()

        data_lines = [
            line[6:] for line in raw.split("\n")
            if line.startswith("data: ") and line.strip() != "data: [DONE]"
        ]
        first_chunk = json.loads(data_lines[0])
        delta = first_chunk["choices"][0]["delta"]
        assert delta.get("role") == "assistant"

    def test_streaming_last_content_chunk_has_finish_reason(self, client):
        """Last content chunk has finish_reason=stop."""
        req = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Finish reason check"}],
            "stream": True,
        }
        with client.stream("POST", "/v1/chat/completions", json=req) as resp:
            raw = resp.read().decode()

        data_lines = [
            line[6:] for line in raw.split("\n")
            if line.startswith("data: ") and line.strip() != "data: [DONE]"
        ]
        # Last non-DONE chunk should have finish_reason
        last_chunk = json.loads(data_lines[-1])
        finish_reason = last_chunk["choices"][0].get("finish_reason")
        assert finish_reason == "stop", f"Expected 'stop', got '{finish_reason}'"

    def test_streaming_cache_control_headers(self, client):
        """SSE response has correct cache-control headers."""
        req = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Headers check"}],
            "stream": True,
        }
        with client.stream("POST", "/v1/chat/completions", json=req) as resp:
            assert "no-cache" in resp.headers.get("cache-control", "").lower()


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Tool Calls
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

class TestToolCalls:

    def _tools_request(self, content="Search for quantum computing") -> dict:
        return {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": content}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "research.search",
                        "description": "Search for research on a topic",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query"}
                            },
                            "required": ["query"],
                        },
                    },
                }
            ],
            "tool_choice": "auto",
        }

    def test_tools_request_accepted(self, client):
        """Request with tools does not error."""
        resp = client.post("/v1/chat/completions", json=self._tools_request())
        assert resp.status_code == 200

    def test_tool_choice_none_respected(self, client):
        """tool_choice=none still returns a normal response."""
        req = {**self._tools_request(), "tool_choice": "none"}
        resp = client.post("/v1/chat/completions", json=req)
        assert resp.status_code == 200
        data = resp.json()
        assert data["choices"][0]["finish_reason"] == "stop"

    def test_tool_translator_openai_to_mcp(self):
        """Tool translator maps OpenAI names to MCP names correctly."""
        from src.api.openai_compat.tool_translator import _resolve_mcp_name
        # Direct alias
        assert _resolve_mcp_name("memory.search") is not None
        assert _resolve_mcp_name("system.status") is not None
        assert _resolve_mcp_name("workflow.run") is not None

    def test_tool_translator_unknown_tool(self):
        """Unknown tool name returns None (not an error)."""
        from src.api.openai_compat.tool_translator import _resolve_mcp_name
        result = _resolve_mcp_name("nonexistent.tool.xyz")
        assert result is None

    def test_dynamic_tools_from_registry(self):
        """build_openai_tools_from_registry returns tools from MCP."""
        from src.api.openai_compat.tool_translator import build_openai_tools_from_registry
        tools = build_openai_tools_from_registry()
        assert isinstance(tools, list)
        assert len(tools) >= 1
        for t in tools:
            assert t["type"] == "function"
            assert "function" in t
            assert "name" in t["function"]
            assert "description" in t["function"]

    def test_parallel_tool_calls_param_ignored_gracefully(self, client):
        """parallel_tool_calls param does not cause error."""
        req = {
            **self._tools_request(),
            "parallel_tool_calls": True,
        }
        resp = client.post("/v1/chat/completions", json=req)
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5: Authentication
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthentication:

    def test_no_auth_mode_allows_all(self, client):
        """With auth_mode=none, requests without headers succeed."""
        # Default config has require_auth=false
        resp = client.get("/v1/models")
        assert resp.status_code == 200

    def test_bearer_token_accepted(self, client):
        """Bearer token header is accepted without error."""
        headers = {"Authorization": "Bearer dm-secret-key-v1"}
        resp = client.get("/v1/models", headers=headers)
        assert resp.status_code == 200

    def test_api_key_header_accepted(self, client):
        """X-API-Key header is accepted without error."""
        headers = {"X-API-Key": "dm-secret-key-v1"}
        resp = client.get("/v1/models", headers=headers)
        assert resp.status_code == 200

    def test_auth_loads_config(self):
        """Auth middleware loads config from openai_security.json."""
        from src.api.openai_compat.auth_middleware import _load_security_config
        cfg = _load_security_config()
        assert isinstance(cfg, dict)
        assert "auth_mode" in cfg


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6: POST /v1/responses
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

class TestResponsesAPI:

    def test_responses_endpoint_exists(self, client):
        """POST /v1/responses returns 200."""
        req = {
            "model": "dm-autonomous-brain",
            "input": "Hello from Responses API",
        }
        resp = client.post("/v1/responses", json=req)
        assert resp.status_code == 200

    def test_responses_format(self, client):
        """Response has OpenAI Responses API format."""
        req = {
            "model": "dm-autonomous-brain",
            "input": "Test input",
        }
        resp = client.post("/v1/responses", json=req)
        data = resp.json()
        assert "id" in data
        assert data["id"].startswith("resp_")
        assert data["object"] == "response"
        assert "output" in data
        assert isinstance(data["output"], list)
        assert len(data["output"]) >= 1
        assert data["status"] == "completed"

    def test_responses_with_instructions(self, client):
        """instructions field (system prompt) is accepted."""
        req = {
            "model": "dm-autonomous-brain",
            "input": "Test question",
            "instructions": "You are a helpful assistant.",
        }
        resp = client.post("/v1/responses", json=req)
        assert resp.status_code == 200

    def test_responses_with_messages(self, client):
        """messages field (fallback) is accepted."""
        req = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Test via messages"}],
        }
        resp = client.post("/v1/responses", json=req)
        assert resp.status_code == 200

    def test_responses_output_has_text(self, client):
        """Output contains text content."""
        req = {"model": "dm-autonomous-brain", "input": "Hello"}
        resp = client.post("/v1/responses", json=req)
        output = resp.json()["output"][0]
        assert output["type"] == "message"
        assert output["role"] == "assistant"
        content = output["content"]
        assert isinstance(content, list)
        assert any(c.get("type") == "output_text" for c in content)


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7: Memory, Identity, Cache Integration
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineIntegration:

    def test_brain_pipeline_is_called(self, client, mock_brain_pipeline):
        """BrainPipeline.process is called for every chat request."""
        req = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Pipeline call test"}],
        }
        client.post("/v1/chat/completions", json=req)
        assert mock_brain_pipeline.called, "BrainPipeline was not called"

    def test_brain_pipeline_called_with_correct_prompt(self, client, mock_brain_pipeline):
        """BrainPipeline receives the user message as user_prompt."""
        test_msg = "Unique pipeline test message 42"
        req = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": test_msg}],
        }
        client.post("/v1/chat/completions", json=req)
        call_kwargs = mock_brain_pipeline.call_args.kwargs
        assert call_kwargs["user_prompt"] == test_msg

    def test_user_id_routing(self, client, mock_brain_pipeline):
        """user field in request is routed to user_id in BrainPipeline."""
        req = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Identity test"}],
            "user": "user_alice",
        }
        client.post("/v1/chat/completions", json=req)
        assert mock_brain_pipeline.call_args.kwargs.get("user_id") == "user_alice"

    def test_memory_context_endpoint_exists(self, client):
        """GET /memory/context (existing endpoint) still works."""
        resp = client.get("/memory/context", headers={"X-API-Key": "dm-secret-key-v1"})
        assert resp.status_code == 200


    def test_brain_pipeline_never_bypassed(self, client, mock_brain_pipeline):
        """N requests → N BrainPipeline calls (no bypassing)."""
        n = 3
        for i in range(n):
            client.post(
                "/v1/chat/completions",
                json={"model": "dm-autonomous-brain", "messages": [{"role": "user", "content": f"msg {i}"}]},
            )
        assert mock_brain_pipeline.call_count == n


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8: Debug Trace System
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

class TestDebugTrace:

    def test_trace_object_creation(self):
        """RequestTrace can be created and steps added."""
        from src.api.openai_compat.debug_trace import RequestTrace
        trace = RequestTrace(request_id="test-id", model="dm-test", user_id="user1")
        trace.add("authentication", "OK", "test")
        trace.add("cache", "MISS")
        trace.add("brain_pipeline", "OK", "completed")
        d = trace.to_dict()
        assert d["request_id"] == "test-id"
        assert len(d["stages"]) == 3
        assert d["stages"][0]["stage"] == "authentication"

    def test_trace_to_headers(self):
        """Trace generates valid HTTP headers."""
        from src.api.openai_compat.debug_trace import RequestTrace
        trace = RequestTrace(request_id="hdr-test", model="dm-autonomous-brain", user_id="user1")
        trace.add("auth", "OK")
        headers = trace.to_headers()
        assert "X-DM-Request-Id" in headers
        assert headers["X-DM-Request-Id"] == "hdr-test"
        assert "X-DM-Pipeline-Ms" in headers

    def test_response_has_debug_headers(self, client):
        """Response includes X-DM-* headers."""
        req = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Debug header test"}],
        }
        resp = client.post("/v1/chat/completions", json=req)
        # Headers should be present (debug_headers=true by default)
        assert "x-dm-request-id" in resp.headers or "X-DM-Request-Id" in resp.headers

    def test_is_debug_mode_returns_bool(self):
        """is_debug_mode() returns a boolean."""
        from src.api.openai_compat.debug_trace import is_debug_mode
        result = is_debug_mode()
        assert isinstance(result, bool)


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9: MCP Integration
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

class TestMCPIntegration:

    def test_mcp_registry_has_tools(self):
        """MCP registry has at least the base tools registered."""
        from src.mcp.registry import mcp_registry
        from src.mcp.tools import register_all_tools
        register_all_tools()
        tools = mcp_registry.list_tools()
        assert len(tools) >= 5
        tool_names = [t["name"] for t in tools]
        assert "system_status" in tool_names
        assert "search_memory" in tool_names
        assert "get_artifacts" in tool_names

    def test_tool_translator_reads_registry_dynamically(self):
        """Tool list from translator matches registry."""
        from src.api.openai_compat.tool_translator import build_openai_tools_from_registry
        from src.mcp.registry import mcp_registry
        from src.mcp.tools import register_all_tools
        register_all_tools()
        registry_count = len(mcp_registry.list_tools())
        oai_tools = build_openai_tools_from_registry()
        assert len(oai_tools) == registry_count

    def test_mcp_tool_execute_system_status(self):
        """MCP system_status tool is callable via translator."""
        import asyncio
        from src.api.openai_compat.tool_translator import execute_openai_tool_call
        result = asyncio.run(
            execute_openai_tool_call(
                tool_call_id="test-call-1",
                oai_function_name="system.status",
                arguments_json="{}",
            )
        )
        assert result["tool_call_id"] == "test-call-1"
        assert result["role"] == "tool"
        content = json.loads(result["content"])
        assert isinstance(content, dict)

    def test_mcp_tool_execute_unknown_returns_error(self):
        """Unknown tool returns error content, not exception."""
        import asyncio
        from src.api.openai_compat.tool_translator import execute_openai_tool_call
        result = asyncio.run(
            execute_openai_tool_call(
                tool_call_id="test-call-unknown",
                oai_function_name="nonexistent.tool",
                arguments_json="{}",
            )
        )
        content = json.loads(result["content"])
        assert "error" in content


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10: Client Compatibility
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

class TestClientCompatibility:
    """
    Verify that request bodies sent by real clients are accepted without error.
    These payloads are representative of what each client actually sends.
    """

    def _post(self, client, payload):
        return client.post("/v1/chat/completions", json=payload)

    def test_grok_build_payload(self, client):
        """Grok Build typical request payload."""
        payload = {
            "model": "dm-autonomous-brain",
            "messages": [
                {"role": "system", "content": "You are a coding assistant."},
                {"role": "user", "content": "Explain async/await in Python"},
            ],
            "temperature": 0.7,
            "stream": False,
            "max_tokens": 2048,
        }
        resp = self._post(client, payload)
        assert resp.status_code == 200
        assert resp.json()["object"] == "chat.completion"

    def test_open_webui_payload(self, client):
        """Open WebUI sends streaming requests with user field."""
        payload = {
            "model": "dm-autonomous-brain",
            "messages": [
                {"role": "user", "content": "What is machine learning?"},
            ],
            "stream": False,
            "user": "open-webui-user-1",
            "temperature": 1.0,
            "max_tokens": 4096,
        }
        resp = self._post(client, payload)
        assert resp.status_code == 200

    def test_cursor_payload(self, client):
        """Cursor sends requests with response_format and seed."""
        payload = {
            "model": "dm-autonomous-brain",
            "messages": [
                {"role": "system", "content": "You are a code completion assistant."},
                {"role": "user", "content": "Complete this Python function: def factorial(n):"},
            ],
            "temperature": 0,
            "seed": 42,
            "response_format": {"type": "text"},
            "max_tokens": 1024,
        }
        resp = self._post(client, payload)
        assert resp.status_code == 200

    def test_cherry_studio_payload(self, client):
        """Cherry Studio includes metadata and frequency_penalty."""
        payload = {
            "model": "dm-autonomous-brain",
            "messages": [
                {"role": "user", "content": "Summarize quantum computing"},
            ],
            "temperature": 0.8,
            "frequency_penalty": 0.3,
            "presence_penalty": 0.1,
            "max_tokens": 2000,
        }
        resp = self._post(client, payload)
        assert resp.status_code == 200

    def test_librechat_payload(self, client):
        """LibreChat sends conversation history with assistant messages."""
        payload = {
            "model": "dm-autonomous-brain",
            "messages": [
                {"role": "user", "content": "What is AI?"},
                {"role": "assistant", "content": "AI stands for Artificial Intelligence..."},
                {"role": "user", "content": "Can you explain more?"},
            ],
            "temperature": 0.7,
            "stream": False,
        }
        resp = self._post(client, payload)
        assert resp.status_code == 200

    def test_continue_dev_payload(self, client):
        """Continue.dev sends code context in messages."""
        payload = {
            "model": "dm-autonomous-brain",
            "messages": [
                {"role": "system", "content": "You are an expert programmer helping with code."},
                {"role": "user", "content": "```python\ndef broken_func(x):\n    return x +\n```\nFix this function."},
            ],
            "temperature": 0.2,
            "max_tokens": 512,
        }
        resp = self._post(client, payload)
        assert resp.status_code == 200

    def test_openai_sdk_v1_payload(self, client):
        """Standard openai Python SDK v1.x chat.completions.create payload."""
        payload = {
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Hello"}],
            "n": 1,
            "stream": False,
            "logprobs": None,
            "top_logprobs": None,
        }
        resp = self._post(client, payload)
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11: Regression — Previous Phase Routes
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

class TestRegression:
    """Ensure all previous platform routes still work after Phase 9."""

    def test_health_endpoint(self, client):
        """GET /health still returns ONLINE."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ONLINE"

    def test_system_status_endpoint(self, client):
        """GET /system/status still accessible."""
        resp = client.get("/system/status")
        # May return 403 if auth required — that's OK for regression
        assert resp.status_code in (200, 403)

    def test_agent_run_endpoint_exists(self, client):
        """POST /agent/run endpoint is still registered."""
        # Send minimal valid request
        resp = client.post(
            "/agent/run",
            json={"agent": "research", "task": "regression test"},
        )
        # 200 or 404 (if agent not found) — both mean endpoint exists
        assert resp.status_code in (200, 404, 403)

    def test_workflow_run_endpoint_exists(self, client):
        """POST /workflow/run endpoint is still registered."""
        resp = client.post(
            "/workflow/run",
            json={"goal": "regression test goal"},
        )
        assert resp.status_code in (200, 403, 500)

    def test_memory_context_endpoint(self, client):
        """GET /memory/context is still accessible."""
        resp = client.get("/memory/context")
        assert resp.status_code in (200, 403)

    def test_memory_store_endpoint(self, client):
        """POST /memory/store is still registered."""
        resp = client.post(
            "/memory/store",
            json={"content": "regression test memory", "category": "test"},
        )
        assert resp.status_code in (200, 403)

    def test_memory_search_endpoint(self, client):
        """POST /memory/search is still registered."""
        resp = client.post(
            "/memory/search",
            json={"query": "regression"},
        )
        assert resp.status_code in (200, 403)

    def test_openai_compat_does_not_shadow_platform_routes(self, client):
        """/health and /v1/models both resolve correctly."""
        health = client.get("/health")
        models = client.get("/v1/models")
        assert health.status_code == 200
        assert models.status_code == 200
        # Different response formats
        assert health.json().get("status") == "ONLINE"
        assert models.json().get("object") == "list"

    def test_docs_still_accessible(self, client):
        """FastAPI /docs Swagger UI still accessible."""
        resp = client.get("/docs")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 12: Schema Validation
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemas:

    def test_chat_completion_request_validates(self):
        """ChatCompletionRequest schema validates a standard request."""
        from src.api.openai_compat.schemas_openai import ChatCompletionRequest
        req = ChatCompletionRequest(
            model="dm-autonomous-brain",
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert req.model == "dm-autonomous-brain"
        assert len(req.messages) == 1

    def test_chat_completion_request_extra_fields_ok(self):
        """Unknown fields in request are stored (extra=allow)."""
        from src.api.openai_compat.schemas_openai import ChatCompletionRequest
        req = ChatCompletionRequest.model_validate({
            "model": "dm-autonomous-brain",
            "messages": [{"role": "user", "content": "Hello"}],
            "totally_unknown_param": "value",
            "another_future_field": 42,
        })
        assert req.model == "dm-autonomous-brain"

    def test_streaming_chunk_schema(self):
        """ChatCompletionChunk validates correctly."""
        from src.api.openai_compat.schemas_openai import ChatCompletionChunk, StreamChoice, DeltaMessage
        chunk = ChatCompletionChunk(
            id="chatcmpl-test",
            model="dm-autonomous-brain",
            choices=[
                StreamChoice(
                    index=0,
                    delta=DeltaMessage(content="Hello"),
                    finish_reason=None,
                )
            ],
        )
        assert chunk.object == "chat.completion.chunk"
        assert chunk.choices[0].delta.content == "Hello"

    def test_model_list_response_schema(self):
        """ModelListResponse validates correctly."""
        from src.api.openai_compat.schemas_openai import ModelListResponse, ModelObject
        resp = ModelListResponse(
            data=[ModelObject(id="test-model", owned_by="test")]
        )
        assert resp.object == "list"
        assert len(resp.data) == 1

    def test_response_request_schema(self):
        """ResponseRequest validates correctly."""
        from src.api.openai_compat.schemas_openai import ResponseRequest
        req = ResponseRequest(
            model="dm-autonomous-brain",
            input="Hello",
            instructions="Be helpful",
        )
        assert req.input == "Hello"
        assert req.instructions == "Be helpful"


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 13: Config Files
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigFiles:

    def _load_json(self, filename):
        import json
        from pathlib import Path
        cfg_path = Path(__file__).resolve().parents[1] / "config" / filename
        assert cfg_path.exists(), f"Config file not found: {cfg_path}"
        return json.loads(cfg_path.read_text(encoding="utf-8"))

    def test_openai_layer_json_exists(self):
        cfg = self._load_json("openai_layer.json")
        assert "base_url" in cfg
        assert "default_model" in cfg
        assert "enable_streaming" in cfg

    def test_models_json_exists(self):
        cfg = self._load_json("models.json")
        assert "virtual_models" in cfg
        assert len(cfg["virtual_models"]) == 8

    def test_openai_security_json_exists(self):
        cfg = self._load_json("openai_security.json")
        assert "auth_mode" in cfg
        assert "require_auth" in cfg


# ─────────────────────────────────────────────────────────────────────────────
# Test runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "--tb=short", "-q"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    sys.exit(result.returncode)
