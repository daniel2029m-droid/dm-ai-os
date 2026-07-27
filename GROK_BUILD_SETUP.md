# Grok Build — Connection Setup Guide
## DM AI Operating System v1.2.0

This guide explains how to connect **Grok Build CLI** and **Grok Build UI** to the DM AI Operating System as the AI backend.

---

## Prerequisites

1. DM AI OS running: `.\start_platform.ps1`
2. Platform responding at `http://localhost:8000/v1`
3. Grok Build installed

---

## Grok Build CLI Configuration

Create or edit `~/.grok/config.json`:

```json
{
  "openai": {
    "base_url": "http://localhost:8000/v1",
    "api_key": "dm-secret-key-v1",
    "model": "dm-autonomous-brain",
    "timeout": 120,
    "stream": true
  }
}
```

### Alternative: Environment Variables

```powershell
$env:OPENAI_BASE_URL = "http://localhost:8000/v1"
$env:OPENAI_API_KEY  = "dm-secret-key-v1"
$env:OPENAI_MODEL    = "dm-autonomous-brain"
```

### Test CLI Connection

```bash
grok chat "Research quantum computing advances in 2025"
```

---

## Grok Build UI Configuration

In Grok Build UI Settings → AI Provider:

| Setting | Value |
|---------|-------|
| Provider | OpenAI Compatible |
| Base URL | `http://localhost:8000/v1` |
| API Key | `dm-secret-key-v1` |
| Model | `dm-autonomous-brain` |
| Stream | Enabled |

---

## Streaming

Grok Build streaming is fully supported. The platform sends SSE chunks in the exact format Grok Build expects:

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"delta":{"content":"..."}}]}
data: [DONE]
```

---

## Models Available

Run in Grok Build CLI:
```bash
grok models list
```

Or query directly:
```bash
curl http://localhost:8000/v1/models | python -m json.tool
```

---

## Tool Calls

Grok Build tool calling is fully supported. Tools are dynamically generated from the MCP registry.

---

## Verify Connection

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer dm-secret-key-v1" \
  -H "Content-Type: application/json" \
  -d '{"model":"dm-autonomous-brain","messages":[{"role":"user","content":"Hello"}],"stream":false}'
```
