# Cherry Studio — Connection Setup Guide
## DM AI Operating System v1.2.0

---

## Add Custom Provider

1. Open Cherry Studio
2. Go to **Settings → Providers**
3. Click **Add Provider**
4. Configure:

| Field | Value |
|-------|-------|
| Provider Name | `DM AI Operating System` |
| API Type | `OpenAI Compatible` |
| Base URL | `http://localhost:8000/v1` |
| API Key | `dm-secret-key-v1` |

5. Click **Test Connection**
6. Go to **Models** and add:
   - `dm-autonomous-brain`
   - `dm-reasoner`
   - `dm-fast`
   - `dm-memory`
   - `dm-research`

---

## JSON Configuration

Cherry Studio stores configuration in `~/.cherry-studio/providers.json`.
Add the following entry:

```json
{
  "id": "dm-ai-os",
  "name": "DM AI Operating System",
  "type": "openai",
  "baseUrl": "http://localhost:8000/v1",
  "apiKey": "dm-secret-key-v1",
  "enabled": true,
  "models": [
    {"id": "dm-autonomous-brain", "name": "DM Autonomous Brain"},
    {"id": "dm-reasoner", "name": "DM Reasoner"},
    {"id": "dm-fast", "name": "DM Fast"},
    {"id": "dm-memory", "name": "DM Memory"},
    {"id": "dm-research", "name": "DM Research"}
  ]
}
```

---

## Features Supported in Cherry Studio

| Feature | Status |
|---------|--------|
| Chat | ✅ |
| Streaming | ✅ |
| System prompt | ✅ |
| Tool calls | ✅ |
| Multiple models | ✅ |
| Memory context | ✅ (via BrainPipeline) |
