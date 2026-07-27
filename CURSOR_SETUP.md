# Cursor — Connection Setup Guide
## DM AI Operating System v1.2.0

---

## Method 1: Cursor Settings UI

1. Open Cursor → **Settings** (Ctrl+,)
2. Navigate to **AI → API Keys**
3. Set **OpenAI API Key**: `dm-secret-key-v1`
4. Set **OpenAI Base URL**: `http://localhost:8000/v1`
5. Select model: `dm-autonomous-brain`

---

## Method 2: `.cursor/mcp.json` (MCP Integration)

Create `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "dm-ai-os": {
      "url": "http://localhost:8001",
      "transport": "http",
      "tools": "all"
    }
  },
  "openai": {
    "baseUrl": "http://localhost:8000/v1",
    "apiKey": "dm-secret-key-v1",
    "model": "dm-autonomous-brain"
  }
}
```

---

## Method 3: Cursor Rules File

Create `.cursorrules` in your project:

```
Use DM AI Operating System at http://localhost:8000/v1
Model: dm-autonomous-brain
API Key: dm-secret-key-v1

This AI backend has:
- Long-term memory across sessions
- Multi-agent orchestration (browser, research, computer)
- Full tool calling via MCP
```

---

## Roo Code / Cline / VSCode Extensions

For any OpenAI-compatible VSCode extension:

```json
{
  "openai.baseUrl": "http://localhost:8000/v1",
  "openai.apiKey": "dm-secret-key-v1",
  "openai.model": "dm-autonomous-brain"
}
```

---

## Verify

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer dm-secret-key-v1" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dm-autonomous-brain",
    "messages": [{"role": "user", "content": "Write a Python hello world"}],
    "stream": false
  }'
```
