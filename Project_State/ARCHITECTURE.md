# ARCHITECTURE DESIGN
**Last Updated:** 2026-07-23T13:09:00-03:00  
**Status:** ✅ FINAL REFINED ARCHITECTURE

---

## 1. System Overview

A provider-agnostic, plugin-driven, DAG-based multi-agent AI Operating System.
Features a lightweight Director Agent, capability-based model selector, independent Workflow Engine, unified Storage Layer, and Plugin architecture.

```
+-----------------------------------------------------------------------------------+
|                                  USER INTERFACE                                   |
|                  (CLI / REST API / VS Code / Optional Web UI)                     |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                              LIGHTWEIGHT DIRECTOR AGENT                           |
|         (Delegates goals to Planner & triggers Workflows - NO business logic)     |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                 CONTEXT MANAGER                                   |
|        (Memory, Project State, File Context, Conversation, Long Tasks)            |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                 PLANNER & DAG ENGINE                              |
|           (Task Decomposition into Directed Acyclic Graphs for Parallel Execution)|
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                  WORKFLOW ENGINE                                  |
|            (Executes reusable, multi-step deterministic workflows independently) |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                    SCHEDULER                                      |
|            (Async Task Queue, Retries, Priority, Non-blocking Execution)          |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                TOOL ROUTER (MCP)                                  |
|        (Deterministic Tool Dispatcher - LLM never executes commands directly)     |
+-----------------------------------------------------------------------------------+
                                          |
        +---------------------------------+---------------------------------+
        |                                                                   |
        v                                                                   v
+-----------------------+                                   +-----------------------+
|  SPECIALIZED AGENTS   | <========= [ EVENT BUS ] =======> |    PLUGIN MANAGER     |
|                       |   (Decoupled Pub/Sub Broker)      |  (FB, WhatsApp, Drive,|
| - Facebook Agent      |                                   |   GitHub, Gmail, etc) |
| - Browser Agent       | <=================================|                       |
| - Content Creator     |                                   |  UNIFIED STORAGE LAYER|
| - Media Generator     | <=================================| (SQLite, Vector,      |
+-----------------------+                                   |  Filesystem, Cache)   |
           |                                                +-----------------------+
           +--------------------------------+--------------------------+
                                            |
                                            v
+-----------------------------------------------------------------------------------+
|                                  GPU MANAGER                                      |
|    (Evaluates task payload → decides if local CPU/iGPU or RunPod GPU needed)     |
+-----------------------------------------------------------------------------------+
                                            |
                                            v
+-----------------------------------------------------------------------------------+
|                             CAPABILITY MODEL SELECTOR                             |
|    (Routes by task type: reasoning, coding, summarization, OCR, planning, etc)   |
|    Cascade: Bonsai 27B 1-bit > Qwen 3 > Qwen 2.5 > Fallback                      |
+-----------------------------------------------------------------------------------+
```

---

## 2. Refined Core Components

### 2.1 Lightweight Director Agent
- **Role:** Pure orchestrator. Accepts user goals, passes context to Planner, and triggers Workflows.
- **Strict Rule:** Zero business logic in Director.

### 2.2 Task Graph (DAG Engine)
- **Role:** Converts high-level plan into a Directed Acyclic Graph.
- **Benefit:** Executes independent nodes concurrently in parallel, maximizing CPU/async efficiency.

### 2.3 Workflow Engine
- **Role:** Runs reusable step-by-step workflows (e.g. video batch generation, social posting pipelines) completely independent of Director Agent.

### 2.4 Unified Storage Layer
- **Unified API wrapping:**
  - **SQLite:** Structured system records & log history.
  - **Vector DB:** Semantic embeddings & memory.
  - **Filesystem:** Media assets, artifacts, state files.
  - **Cache Layer:** SHA-256 hash-indexed query/LLM cache.

### 2.5 Plugin Manager
- **Role:** Modular extension architecture for third-party tools & APIs (Facebook, WhatsApp, Telegram, Gmail, Google Drive, GitHub).
- **Rule:** New integrations are added as self-contained plugins in `src/plugins/` without modifying core code.

### 2.6 Capability-Based Dynamic Model Selector
- **Role:** Inspects task requirement (`task_type="coding"|"reasoning"|"ocr"|"planning"|"summarization"`) and routes to optimal model backend.
