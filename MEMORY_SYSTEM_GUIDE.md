# PERSISTENT MEMORY & PERSONAL AI BRAIN GUIDE (PHASE 8)

This guide documents the **Persistent AI Brain Layer** integrated into the DM Autonomous Orchestration Platform (`v1.1.0-production`).

---

## 1. Architecture Overview

```text
               USER / GROK BUILD UI
                        |
                    MCP / API
                        |
             DIRECTOR & AGENTS
                        |
       +----------------+----------------+
       |                                 |
SHORT-TERM MEMORY               MEMORY BRAIN MANAGER
(Session History & Active Tasks)         |
                                 +-------+-------+
                                 |               |
                         LONG-TERM MEMORY   USER IDENTITY
                         (SQLite + Vectors) (Profile DB)
```

---

## 2. Subsystem Components

### A. Short-Term Memory (`src/memory/short_term_memory.py`)
- Manages real-time conversation turns and active workflow states in memory via `ContextManager`.

### B. Long-Term Memory (`src/memory/long_term_memory.py`)
- Persistent memory store located at `Project_State/Memory/memory.db`.
- Stores importance rating, content, category, and timestamp.

### C. Embedding Engine & Knowledge Store (`src/memory/embedding_engine.py` & `knowledge_store.py`)
- Generates 768-dimensional text embeddings using Ollama (`nomic-embed-text`) with automatic fallback.
- Stores vector index data in `Project_State/Memory/vectors/vector_index.json`.

### D. User Identity System (`src/users/`)
- Persists user preferences, projects, tools, and goals in `Project_State/Storage/users.db`.
- Default Profile: `user_id="daniel"` (Name: Daniel, Preferences: Spanish, AI automation, Ollama, n8n, CapCut).

---

## 3. API Endpoints

- `GET /memory/profile?user_id=daniel` — Get user profile & preferences.
- `POST /memory/store` — Store new long-term memory (`{"content": "...", "category": "..."}`).
- `POST /memory/search` — Search memory (`{"query": "...", "category": "..."}`).
- `POST /memory/forget` — Delete a memory by ID (`{"memory_id": 1}`).
- `GET /memory/context?query=automation` — Retrieve formatted system context prompt.

---

## 4. MCP Server Memory Tools

- `get_user_profile(user_id)`
- `remember(content, category, importance)`
- `search_memory(query, category)`
- `update_memory(key, value, user_id)`
- `forget_memory(memory_id)`
- `get_context(user_id, query)`

---

## 5. Export, Backup & Safety
- **Export Memory**: Saved to `Project_State/Memory/memory_export.json`
- **Backup Memory**: Saved to `Project_State/Memory/memory_backup.json`
