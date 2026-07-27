# Grok Build Configuration Reference
## DM AI Operating System v1.3.0-production

This guide details the `~/.grok/config.toml` structure generated and safely merged by the DM AI Operating System.

---

## 1. Complete `~/.grok/config.toml` Example

```toml
# ============================================================
# DM AI Operating System — Native Grok Build Models
# Auto-generated configuration for DM AI OS v1.3.0
# ============================================================

[models]
default = "dm-autonomous-brain"

[model.dm-autonomous-brain]
model = "dm-autonomous-brain"
name = "DM Autonomous Brain"
base_url = "http://localhost:8000/v1"
api_backend = "chat_completions"
context_window = 32768
temperature = 0.2
stream_tool_calls = true

[model.dm-reasoner]
model = "dm-reasoner"
name = "DM Reasoner"
base_url = "http://localhost:8000/v1"
api_backend = "chat_completions"
context_window = 32768
temperature = 0.2
stream_tool_calls = true

[model.dm-fast]
model = "dm-fast"
name = "DM Fast"
base_url = "http://localhost:8000/v1"
api_backend = "chat_completions"
context_window = 8192
temperature = 0.5
stream_tool_calls = true

[model.dm-memory]
model = "dm-memory"
name = "DM Memory"
base_url = "http://localhost:8000/v1"
api_backend = "chat_completions"
context_window = 32768
temperature = 0.3
stream_tool_calls = true

[model.dm-browser]
model = "dm-browser"
name = "DM Browser Agent"
base_url = "http://localhost:8000/v1"
api_backend = "chat_completions"
context_window = 16384
temperature = 0.3
stream_tool_calls = true

[model.dm-research]
model = "dm-research"
name = "DM Deep Research"
base_url = "http://localhost:8000/v1"
api_backend = "chat_completions"
context_window = 32768
temperature = 0.2
stream_tool_calls = true

[model.dm-media]
model = "dm-media"
name = "DM Media Agent"
base_url = "http://localhost:8000/v1"
api_backend = "chat_completions"
context_window = 8192
temperature = 0.7
stream_tool_calls = true

[model.dm-facebook]
model = "dm-facebook"
name = "DM Social Content"
base_url = "http://localhost:8000/v1"
api_backend = "chat_completions"
context_window = 8192
temperature = 0.7
stream_tool_calls = true
```

---

## 2. Safe Merging Rules

- Existing `~/.grok/config.toml` files are **never overwritten**.
- The platform scans for `[model.dm-autonomous-brain]`. If present, no action is taken.
- If missing, the DM model configuration block is appended to the bottom of `config.toml`.
- Any existing custom models or API keys configured by the user are preserved 100%.
