# Grok Build Virtual Model Catalog
## DM AI Operating System v1.3.0-production

The DM AI Operating System exposes 8 virtual model aliases to Grok Build. All 8 models route internally into `BrainPipeline`.

---

## Model Overview

| Model ID | Description | Default Temperature | Context Window | Internal Routing Capability |
|----------|-------------|---------------------|----------------|----------------------------|
| `dm-autonomous-brain` | Full orchestration (memory + agents + DAG + LLM) | 0.2 | 32,768 | `reasoning` |
| `dm-reasoner` | Deep reasoning and multi-step planning | 0.2 | 32,768 | `planning` |
| `dm-fast` | Ultra-fast summarization & quick chat | 0.5 | 8,192 | `summarization` |
| `dm-memory` | Memory-augmented conversational model | 0.3 | 32,768 | `reasoning` |
| `dm-browser` | Web search and browser agent routing | 0.3 | 16,384 | `general` |
| `dm-research` | Academic synthesis & deep research | 0.2 | 32,768 | `planning` |
| `dm-media` | Visual asset & image generation routing | 0.7 | 8,192 | `general` |
| `dm-facebook` | Social media post generator | 0.7 | 8,192 | `general` |

---

## Routing Architecture

```
Grok Build Request (model: "dm-autonomous-brain")
        │
        ▼
   POST /v1/chat/completions
        │
        ▼
  BrainPipeline.process()
        │
        ├── 1. Identity Manager
        ├── 2. Memory Retriever
        ├── 3. Tool Selector
        ├── 4. Workflow Engine / Task DAG
        ├── 5. LLM Router (Ollama capability selection)
        └── 6. Memory Writer & Cache
```
