# Continue.dev — Connection Setup Guide
## DM AI Operating System v1.2.0

---

## `~/.continue/config.json`

Add the DM AI OS as a model provider:

```json
{
  "models": [
    {
      "title": "DM Autonomous Brain",
      "provider": "openai",
      "model": "dm-autonomous-brain",
      "apiBase": "http://localhost:8000/v1",
      "apiKey": "dm-secret-key-v1",
      "contextLength": 32768,
      "completionOptions": {
        "temperature": 0.7,
        "maxTokens": 2048
      }
    },
    {
      "title": "DM Reasoner",
      "provider": "openai",
      "model": "dm-reasoner",
      "apiBase": "http://localhost:8000/v1",
      "apiKey": "dm-secret-key-v1",
      "contextLength": 32768
    },
    {
      "title": "DM Fast",
      "provider": "openai",
      "model": "dm-fast",
      "apiBase": "http://localhost:8000/v1",
      "apiKey": "dm-secret-key-v1",
      "contextLength": 8192
    }
  ],
  "tabAutocompleteModel": {
    "title": "DM Fast (Autocomplete)",
    "provider": "openai",
    "model": "dm-fast",
    "apiBase": "http://localhost:8000/v1",
    "apiKey": "dm-secret-key-v1"
  },
  "embeddingsProvider": {
    "provider": "openai",
    "model": "dm-fast",
    "apiBase": "http://localhost:8000/v1",
    "apiKey": "dm-secret-key-v1"
  }
}
```

---

## VSCode settings.json (if using Continue VSCode extension)

```json
{
  "continue.apiKey": "dm-secret-key-v1",
  "continue.apiBase": "http://localhost:8000/v1",
  "continue.model": "dm-autonomous-brain"
}
```

---

## Features

| Continue.dev Feature | Status |
|---------------------|--------|
| Chat | ✅ |
| Inline completions | ✅ |
| Code editing | ✅ |
| Streaming | ✅ |
| Context files | ✅ |
| Tool use | ✅ |

---

## Verify

Press `Ctrl+Shift+P` → "Continue: Open Chat" in VSCode.
Type a message. The DM AI OS brain will respond.
