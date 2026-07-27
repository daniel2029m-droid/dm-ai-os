# OpenAI Compatibility — DM AI Operating System v1.2.0

## Overview

The DM AI Operating System exposes a **complete OpenAI-compatible REST API** starting at Phase 9.

Any application that works with OpenAI's API works with this platform **without modification**.

The OpenAI layer is a pure translation layer. All intelligence lives in the BrainPipeline.

---

## Architecture

```
OpenAI Client (Grok Build / Cursor / Open WebUI / LibreChat / any)
        │
        ▼  HTTP (OpenAI-format JSON)
┌──────────────────────────────────────────┐
│  OpenAI Compatibility Layer              │
│  src/api/openai_compat/                  │
│  • Auth (Bearer / X-API-Key / none)      │
│  • Schema validation (extra fields OK)   │
│  • Tool call translation → MCP           │
│  • SSE streaming                         │
│  • Response formatting                   │
└──────────────┬───────────────────────────┘
               │  delegate
               ▼
┌──────────────────────────────────────────┐
│  BrainPipeline (the brain)               │
│  Auth → Cache → Identity → Memory →      │
│  Knowledge → Context → Tool Selector →   │
│  Workflow → DAG → Agent → LLM → Writer   │
└──────────────────────────────────────────┘
```

---

## Base URL

```
http://localhost:8000/v1
```

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/v1/models` | List available models |
| `POST` | `/v1/chat/completions` | Chat completions (streaming + tools) |
| `POST` | `/v1/responses` | Responses API (openai SDK v1.x+) |
| `GET`  | `/health` | Health check |
| `GET`  | `/system/status` | Full system status |
| `GET`  | `/memory/context` | Current memory context |
| `POST` | `/agent/run` | Direct agent execution |
| `POST` | `/workflow/run` | Multi-agent workflow |

---

## Models

| Model ID | Description |
|----------|-------------|
| `dm-autonomous-brain` | Full orchestration: memory + agents + DAG + LLM |
| `dm-reasoner` | Deep reasoning and planning |
| `dm-fast` | Fast summarization |
| `dm-memory` | Memory-augmented conversations |
| `dm-browser` | Web browsing + search augmented |
| `dm-research` | Deep research and synthesis |
| `dm-media` | Media generation coordination |
| `dm-facebook` | Social media content |

All models internally route to BrainPipeline.

---

## Chat Completions

### Non-streaming

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dm-autonomous-brain",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Research the latest in quantum computing"}
    ],
    "temperature": 0.7,
    "max_tokens": 1024
  }'
```

### Streaming (SSE)

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dm-autonomous-brain",
    "messages": [{"role": "user", "content": "Explain machine learning"}],
    "stream": true
  }'
```

Response format:
```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Machine"},"finish_reason":null}]}

data: [DONE]
```

### With Tool Calls

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dm-autonomous-brain",
    "messages": [{"role": "user", "content": "Search for information about AI"}],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "research.search",
          "description": "Search for research on a topic",
          "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}
        }
      }
    ]
  }'
```

---

## Supported Parameters

| Parameter | Support |
|-----------|---------|
| `model` | ✅ Full |
| `messages` | ✅ Full (system/user/assistant/tool) |
| `temperature` | ✅ Passed through |
| `top_p` | ✅ Passed through |
| `stream` | ✅ Full SSE |
| `stop` | ✅ Gracefully handled |
| `max_tokens` | ✅ Passed through |
| `tools` | ✅ Translated to MCP |
| `tool_choice` | ✅ Respected |
| `parallel_tool_calls` | ✅ Gracefully handled |
| `response_format` | ✅ Gracefully handled |
| `n` | ✅ Multiple completions |
| `seed` | ✅ Gracefully handled |
| `presence_penalty` | ✅ Gracefully handled |
| `frequency_penalty` | ✅ Gracefully handled |
| `user` | ✅ Identity routing |
| `metadata` | ✅ Stored |
| `store` | ✅ Gracefully handled |
| `reasoning` | ✅ Gracefully handled |
| Unknown fields | ✅ Silently ignored |

---

## Authentication

Configure in `config/openai_security.json`:

```json
{
  "auth_mode": "none",
  "require_auth": false
}
```

### No Auth (default for local dev)
```
auth_mode: "none"
```

### Bearer Token
```
auth_mode: "bearer"
Authorization: Bearer dm-secret-key-v1
```

### API Key
```
auth_mode: "api_key"
X-API-Key: dm-secret-key-v1
```

### Both (accept either)
```
auth_mode: "both"
```

---

## Debug Mode

Enable in `config/openai_layer.json`:
```json
{"enable_debug_mode": true, "debug_headers": true}
```

Each response includes `X-DM-*` headers showing pipeline execution:
```
X-DM-Request-Id: chatcmpl-abc123
X-DM-Pipeline-Ms: 1247
X-DM-Stages: 12
X-DM-Model: dm-autonomous-brain
X-DM-User: daniel
```

---

## Tool Mapping

| OpenAI Tool Name | MCP Tool |
|-----------------|---------|
| `browser.search` | `browser_search` |
| `browser.open` | `browser_open` |
| `computer.execute` | `computer_execute` |
| `research.search` | `research_search` |
| `research.summarize` | `research_summarize` |
| `workflow.run` | `run_workflow` |
| `agent.run` | `run_agent` |
| `memory.search` | `search_memory` |
| `memory.store` | `remember` |
| `memory.update` | `update_memory` |
| `memory.forget` | `forget_memory` |
| `artifacts.list` | `get_artifacts` |
| `system.status` | `system_status` |

Future MCP tools appear automatically — no code changes required.

---

## Phase 10 — Reserved Endpoints (not yet implemented)

| Endpoint | Purpose |
|----------|---------|
| `POST /v1/embeddings` | Text embedding generation |
| `POST /v1/images` | Image generation |
| `POST /v1/audio/transcriptions` | Audio transcription |
| `POST /v1/audio/speech` | Text-to-speech |
| `POST /v1/files` | File management |

The architecture supports adding these without changes to the existing layer.
