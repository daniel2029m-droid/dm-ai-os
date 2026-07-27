# DECISIONS
**Last Updated:** 2026-07-23T13:14:00-03:00

> Closed decisions are FINAL. Never re-open without a documented technical reason.

---

## D-001 — Project State System
**Status:** ✅ CLOSED | **Decision:** All project memory lives in `/Project_State/`. Every session starts by reading state files.

## D-002 — Maximum Reuse Principle
**Status:** ✅ CLOSED | **Decision:** Reuse existing code (`agent_browser.py`, `comfy_api.py`, `orchestrator.py`, `agents.py`, `Ollama`, `Playwright`) before writing new code.

## D-003 — Resource & Budget Principle
**Status:** ✅ CLOSED | **Decision:** Minimize RAM, CPU, GPU, disk, tokens, and RunPod credits ($10 budget cap).

## D-004 — Provider-Agnostic Architecture
**Status:** ✅ CLOSED | **Decision:** All providers (LLM, browser, vector DB, GPU) abstracted behind uniform interfaces.

## D-005 — Reasoning vs. Execution Scoping
**Status:** ✅ CLOSED | **Decision:** Local models for reasoning/planning; RunPod exclusively for GPU media rendering.

## D-006 — Security & Secrets Management
**Status:** ✅ CLOSED | **Decision:** Secrets stored in environment / Credential Manager.

## D-007 — Dynamic Model Selector & Capability Routing
**Status:** ✅ CLOSED | **Decision:** Model Selector uses capability-based routing (task_type) + priority cascade.

## D-008 — Context Manager & Scheduler Integration
**Status:** ✅ CLOSED | **Decision:** Context Manager controls state/file/task memory; Scheduler controls async task queues and retries.

## D-009 — Unified Storage Layer
**Status:** ✅ CLOSED | **Decision:** Unified Storage Manager wraps SQLite, Vector DB, Filesystem, and SHA-256 Cache under one clean interface.

## D-010 — Event Bus & GPU Manager Architecture
**Status:** ✅ CLOSED | **Decision:** Event-driven pub/sub communication; GPU Manager strictly controls RunPod spend.

## D-011 — Workflow Engine & Lightweight Director
**Status:** ✅ CLOSED | **Decision:** Director is lightweight (triggers workflows & planner); Workflow Engine executes multi-step tasks independently.

## D-012 — Plugin Manager Architecture
**Status:** ✅ CLOSED | **Decision:** Integrations added as plugins without altering core.

## D-013 — Task Graph (DAG) Execution
**Status:** ✅ CLOSED | **Decision:** Tasks structured as DAGs for parallel execution.

## D-014 — ARCHITECTURE FREEZE & TDD METHODOLOGY
**Status:** ✅ CLOSED | **Decision:** Architecture is frozen. Prioritize working software over design. TDD workflow: (1) Test -> (2) Implement -> (3) Verify -> (4) Update State -> (5) Next.
