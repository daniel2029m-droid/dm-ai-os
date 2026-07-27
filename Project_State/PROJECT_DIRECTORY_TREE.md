# Complete Project Directory Tree & File Purpose Map

Below is the complete tree of all directories and files in the workspace, along with a single-sentence purpose description for every file.

```
scratch/
├── Project_State/
│   ├── Artifacts/
│   ├── Audit/
│   │   ├── acceptance_results.json
│   │   ├── e2e_workflow_report.json
│   │   ├── performance_audit.json
│   │   ├── real_validation_results.json
│   │   └── real_world_benchmarks.json
│   ├── Cache/
│   ├── Storage/
│   │   └── knowledge.db
│   ├── ARCHITECTURE.md
│   ├── CHANGELOG.md
│   ├── DECISIONS.md
│   ├── DEPENDENCIES.md
│   ├── INSTALLED_COMPONENTS.md
│   ├── MODELS.md
│   ├── PRODUCTION_READINESS_REPORT.md
│   ├── PROJECT_DIRECTORY_TREE.md
│   ├── PROJECT_STATE.md
│   ├── ROADMAP.md
│   ├── RUNPOD_STATUS.md
│   ├── SYSTEM_INVENTORY.md
│   ├── TASKS.md
│   ├── TODO.md
│   ├── _audit.ps1
│   ├── _check.ps1
│   ├── _psver.ps1
│   ├── audit.ps1
│   └── reuse_audit.ps1
├── src/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── browser_agent.py
│   │   ├── computer_agent.py
│   │   ├── director.py
│   │   ├── facebook_agent.py
│   │   ├── media_agent.py
│   │   ├── research_agent.py
│   │   └── university_agent.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── cache_layer.py
│   │   ├── context_manager.py
│   │   ├── dag_engine.py
│   │   ├── event_bus.py
│   │   ├── gpu_manager.py
│   │   ├── plugin_manager.py
│   │   ├── scheduler.py
│   │   └── workflow_engine.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── capability_selector.py
│   │   └── model_selector.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── knowledge_base.py
│   │   └── storage_layer.py
│   ├── __init__.py
│   └── main.py
├── tests/
│   ├── phase2_5_acceptance_tests.py
│   ├── test_browser_agent.py
│   ├── test_computer_agent.py
│   ├── test_facebook_agent.py
│   ├── test_media_agent.py
│   ├── test_performance_audit.py
│   ├── test_phase3_integration.py
│   ├── test_phase4_e2e_workflow.py
│   ├── test_phase4_real_validation.py
│   ├── test_research_agent.py
│   └── test_university_agent.py
└── USER_MANUAL.md
```

---

## File Purpose Map (Single-Sentence Descriptions)

### Root Directory
- **`src/main.py`**: Production CLI entry point for executing goals, triggering plugins, listing registered modules, and checking system status.
- **`src/__init__.py`**: Root Python package declaration for the AI Operating System codebase.
- **`USER_MANUAL.md`**: Complete 15-section operational user manual providing end-to-end instructions for setup, configuration, CLI usage, agent operations, and troubleshooting.

---

### Agent Modules (`src/agents/`)
- **`src/agents/__init__.py`**: Package re-exports for all specialized agent classes and the Director Agent.
- **`src/agents/browser_agent.py`**: Cognitive browser automation agent powered by Playwright and local LLM perception with explicit user safety gates.
- **`src/agents/computer_agent.py`**: Local OS environment, process management, and system diagnostics agent enforcing human approval before destructive CLI actions.
- **`src/agents/director.py`**: Lightweight orchestrator agent that receives high-level user goals and delegates to Planner TaskDAGs or Workflow Engine without carrying business logic.
- **`src/agents/facebook_agent.py`**: Social media strategy, copywriting, hashtag generation, and editorial planning agent enforcing a mandatory post publication approval gate.
- **`src/agents/media_agent.py`**: GPU-accelerated image and video generation agent supporting RunPod and ComfyUI Cloud APIs under a $10 budget cap.
- **`src/agents/research_agent.py`**: Technical research, document analysis, and topic summarization agent backed by SHA-256 caching for zero-token repeat queries.
- **`src/agents/university_agent.py`**: Academic tutoring, study guide creation, exam preparation, and complex concept explanation agent.

---

### Core Infrastructure Modules (`src/core/`)
- **`src/core/__init__.py`**: Core package re-exports for event bus, scheduler, DAG engine, workflow engine, context manager, and plugin manager.
- **`src/core/cache_layer.py`**: SHA-256 hash-indexed query cache eliminating redundant local LLM calls and web searches.
- **`src/core/context_manager.py`**: Manages session conversation history windows, active task states, and project state markdown file persistence.
- **`src/core/dag_engine.py`**: Directed Acyclic Graph execution engine running topological node batches concurrently with per-node timeout protection.
- **`src/core/event_bus.py`**: Decoupled Pub/Sub event broker supporting wildcard topic subscriptions and a dead-letter queue for failed subscribers.
- **`src/core/gpu_manager.py`**: Workload evaluator that routes heavy media rendering to remote RunPod GPUs while enforcing a strict $10 spend ceiling.
- **`src/core/plugin_manager.py`**: Extensible plugin registration and action invocation system enabling modular third-party integrations.
- **`src/core/scheduler.py`**: Asynchronous task queue manager supporting retry backoff policies and background worker execution.
- **`src/core/workflow_engine.py`**: Multi-step deterministic workflow runner executing multi-agent pipelines independently of the Director Agent.

---

### Model Provider Modules (`src/providers/`)
- **`src/providers/__init__.py`**: Providers package re-exports for capability selection.
- **`src/providers/capability_selector.py`**: Dynamic model selector that probes local Ollama endpoints and routes tasks to optimal backends based on required capabilities.
- **`src/providers/model_selector.py`**: Probing and cascading fallback utility for local model backends.

---

### Storage Modules (`src/storage/`)
- **`src/storage/__init__.py`**: Storage package re-exports for knowledge base and unified storage layer.
- **`src/storage/knowledge_base.py`**: SQLite database interface managing structured semantic records and system event history.
- **`src/storage/storage_layer.py`**: Unified storage manager wrapping SQLite, SHA-256 Cache, Filesystem artifacts, and connection cleanup.

---

### Test Harnesses (`tests/`)
- **`tests/phase2_5_acceptance_tests.py`**: Real-world acceptance test suite verifying all 6 specialized agents against end-to-end scenarios.
- **`tests/test_browser_agent.py`**: Unit test verifying BrowserAgent DOM perception parsing and safety check.
- **`tests/test_computer_agent.py`**: Unit test verifying ComputerAgent OS information retrieval and command safety block.
- **`tests/test_facebook_agent.py`**: Unit test verifying FacebookAgent copywriting and post approval safety gate.
- **`tests/test_media_agent.py`**: Unit test verifying MediaAgent ComfyUI payload structure and GPU target evaluation.
- **`tests/test_performance_audit.py`**: Performance audit script measuring component latencies, event throughput, and RAM footprint.
- **`tests/test_phase3_integration.py`**: End-to-end integration test suite exercising 11 multi-module pipeline scenarios.
- **`tests/test_phase4_e2e_workflow.py`**: Real-world end-to-end execution script for the "Facebook post from idea to final image" scenario.
- **`tests/test_phase4_real_validation.py`**: Subsystem validation harness executing real components and classifying readiness status.
- **`tests/test_research_agent.py`**: Unit test verifying ResearchAgent report generation and cache hit reuse.
- **`tests/test_university_agent.py`**: Unit test verifying UniversityAgent concept explanation and study guide creation.

---

### Project State Documentation (`Project_State/`)
- **`Project_State/ARCHITECTURE.md`**: Comprehensive architectural specification detailing system overview, DAG engine, storage layer, and model routing cascades.
- **`Project_State/CHANGELOG.md`**: Chronological log tracking major project milestones, phase completions, and code additions.
- **`Project_State/DECISIONS.md`**: Architectural Decision Records (ADR) documenting design decisions, constraints, and trade-offs.
- **`Project_State/DEPENDENCIES.md`**: Complete list of required Python packages, system dependencies, and runtime tools.
- **`Project_State/INSTALLED_COMPONENTS.md`**: Audit inventory of verified software installations on the host system.
- **`Project_State/MODELS.md`**: Inventory of local Ollama models and cloud GPU endpoints with priority cascade orders.
- **`Project_State/PRODUCTION_READINESS_REPORT.md`**: Definitive 15-section production readiness assessment, empirical benchmarks, and sign-off.
- **`Project_State/PROJECT_DIRECTORY_TREE.md`**: Complete workspace directory tree and single-sentence file purpose map.
- **`Project_State/PROJECT_STATE.md`**: High-level summary of current project status, phase progression, and operational readiness.
- **`Project_State/ROADMAP.md`**: Strategic development roadmap outlining completed milestones and future phases.
- **`Project_State/RUNPOD_STATUS.md`**: Cloud GPU budget tracker, pod pricing breakdown, and remote API configuration status.
- **`Project_State/SYSTEM_INVENTORY.md`**: Hardware inventory documenting CPU cores, RAM, local iGPU, storage, OS, and software versions.
- **`Project_State/TASKS.md`**: Task tracker detailing phase objectives, deliverables, and completion status.
- **`Project_State/TODO.md`**: Immediate operational task checklist.
- **`Project_State/audit.ps1`**: Read-only PowerShell script for collecting system hardware, software, and environment metrics into JSON files.
- **`Project_State/reuse_audit.ps1`**: Read-only PowerShell script for scanning existing local projects and agent assets to maximize reuse.
- **`Project_State/_audit.ps1`**: Legacy PowerShell script for initial system inventory checks.
- **`Project_State/_check.ps1`**: PowerShell diagnostic check script for testing execution context.
- **`Project_State/_psver.ps1`**: Diagnostic script for checking PowerShell version compatibility.
- **`Project_State/Audit/acceptance_results.json`**: Empirical results from the Phase 2.5 acceptance test execution.
- **`Project_State/Audit/e2e_workflow_report.json`**: Execution report for the Phase 4 end-to-end Facebook campaign workflow.
- **`Project_State/Audit/performance_audit.json`**: Measured component latencies, event throughput, and RAM metrics from the Phase 3 audit.
- **`Project_State/Audit/real_validation_results.json`**: Empirical classification results for all 16 subsystems from the Phase 4 validation harness.
- **`Project_State/Audit/real_world_benchmarks.json`**: Consolidated real-world benchmarks, resource consumption, and token savings report.
- **`Project_State/Storage/knowledge.db`**: Persistent SQLite database storing semantic project records and system event logs.
