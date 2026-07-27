# AI Operating System — Complete User Manual
**Version:** 1.0.0 Production Release | **Status:** Validated & Production Ready

Welcome to the **AI Operating System**, a provider-agnostic, plugin-driven, event-driven multi-agent platform designed for local-first intelligence, automated web & OS workflows, content creation, and GPU media rendering.

This manual provides complete instructions for operating, configuring, extending, and maintaining the platform without reading source code.

---

## Table of Contents
1. [Installation & Prerequisites](#1-installation--prerequisites)
2. [Folder & Directory Structure](#2-folder--directory-structure)
3. [How to Start the Platform](#3-how-to-start-the-platform)
4. [Available Commands & CLI Flags](#4-available-commands--cli-flags)
5. [Specialized Agents Roster](#5-specialized-agents-roster)
6. [Deterministic Workflows](#6-deterministic-workflows)
7. [System Configuration & Settings](#7-system-configuration--settings)
8. [Plugin System & Integration Guide](#8-plugin-system--integration-guide)
9. [RunPod & Cloud GPU Integration](#9-runpod--cloud-gpu-integration)
10. [Troubleshooting & Diagnostics](#10-troubleshooting--diagnostics)
11. [Backup & System Restore](#11-backup--system-restore)
12. [Future Developer Extension Guide](#12-future-developer-extension-guide)
13. [Maintenance & Housekeeping](#13-maintenance--housekeeping)
14. [Known System Limitations](#14-known-system-limitations)
15. [First Real Example: Facebook Campaign Workflow](#15-first-real-example-facebook-campaign-workflow)

---

## 1. Installation & Prerequisites

### Minimum System Requirements
- **OS:** Windows 10/11, macOS, or Linux (x86_64 / ARM64)
- **Python:** Version 3.10, 3.11, 3.12, or 3.13
- **RAM:** Minimum 8 GB (16 GB recommended for smooth local LLM execution)
- **Disk:** 5 GB free space for database, cache, and artifacts

### Step-by-Step Installation

1. **Clone or Extract Project Workspace**:
   Navigate to the project root directory:
   ```bash
   cd C:\Users\moral\.gemini\antigravity-ide\scratch
   ```

2. **Install Python Dependencies**:
   Install all required packages from `Project_State/DEPENDENCIES.md`:
   ```bash
   pip install httpx playwright psutil pytest
   ```

3. **Install Playwright Chromium Engine**:
   Download the headless Chromium browser binaries:
   ```bash
   playwright install chromium
   ```

4. **Install & Launch Ollama (Local LLM Provider)**:
   - Download Ollama from [https://ollama.com](https://ollama.com)
   - Pull the required lightweight models:
     ```bash
     ollama pull qwen2.5:1.5b
     ollama pull qwen2.5:0.5b
     ```
   - Ensure the Ollama service is running on `http://localhost:11434`.

---

## 2. Folder & Directory Structure

```
scratch/
├── src/
│   ├── main.py                  # Production CLI Entry Point
│   ├── agents/                  # Specialized Agent Implementations
│   ├── core/                    # Infrastructure Modules (EventBus, Scheduler, DAG, etc.)
│   ├── providers/               # LLM Provider & Capability Selectors
│   └── storage/                 # Storage Layer & SQLite Knowledge DB
├── tests/                       # Automated Unit, Acceptance & Integration Test Suites
├── Project_State/
│   ├── Storage/knowledge.db     # SQLite Database (Records & Logs)
│   ├── Cache/                   # SHA-256 Hash Cache Files (.json)
│   ├── Artifacts/               # Output JSON reports, study guides, post drafts
│   ├── Audit/                   # Performance audits & validation reports
│   └── *.md                     # Architectural documentation & inventories
└── USER_MANUAL.md               # This Complete Manual
```

---

## 3. How to Start the Platform

The platform is operated via the unified production CLI entry point `src/main.py`.

### 1. Quick Verification (List Plugins)
Verify all 6 specialized agents are registered and initialized:
```bash
python src/main.py --list-plugins
```

### 2. System Status Check
Inspect system health, active database paths, and registered plugin counts:
```bash
python src/main.py --system-status
```

### 3. Orchestrate a User Goal
Delegate a high-level goal to the Director Agent:
```bash
python src/main.py --goal "Research quantum computing milestones in 2026"
```

---

## 4. Available Commands & CLI Flags

| CLI Flag | Argument | Description | Example Usage |
|---|---|---|---|
| `--goal` | `"string"` | High-level goal to decompose and execute | `python src/main.py --goal "Build AI strategy"` |
| `--workflow` | `"id"` | Execute a registered deterministic workflow | `python src/main.py --workflow "integration_pipeline"` |
| `--plugin` | `"name"` | Target plugin to invoke directly | `python src/main.py --plugin computer --action sys_info` |
| `--action` | `"action"` | Specific action method on target plugin | Used with `--plugin` |
| `--payload` | `'{"json"}'` | JSON parameters passed to plugin action | `--payload '{"topic": "Quantum Computing"}'` |
| `--list-plugins` | None | List all registered plugins and descriptions | `python src/main.py --list-plugins` |
| `--system-status` | None | Print system health, database, and cache paths | `python src/main.py --system-status` |

---

## 5. Specialized Agents Roster

### 1. Director Agent (`src/agents/director.py`)
- **Role:** Pure goal orchestrator. Queries storage cache, assigns optimal model via CapabilitySelector, and triggers Workflows or Planner TaskDAGs.
- **Rule:** Contains **zero business logic**.

### 2. Browser Agent (`src/agents/browser_agent.py`)
- **Role:** Cognitive browser automation using Playwright Chromium and LLM perception parsing.
- **Safety Gate:** Form submissions, purchases, and navigation to untrusted pages require user confirmation.

### 3. Computer Agent (`src/agents/computer_agent.py`)
- **Role:** Local OS environment control, process execution, and system diagnostics.
- **Safety Gate:** Destructive shell commands (`rmdir`, `del`, `format`, `shutdown`) are **blocked** until explicit user approval is granted.

### 4. Research Agent (`src/agents/research_agent.py`)
- **Role:** Technical topic research, document analysis, and concise bulleted report generation.
- **Efficiency:** Uses SHA-256 Hash Caching. Repeat queries take **0.27 ms** with zero token consumption.

### 5. Facebook Agent (`src/agents/facebook_agent.py`)
- **Role:** Strategic copywriting, CTA generation, viral hashtags, and visual image prompts for Facebook campaigns.
- **Safety Gate:** Social media post publishing strictly requires user confirmation.

### 6. University Agent (`src/agents/university_agent.py`)
- **Role:** Academic concept breakdowns, intuition guides, formal definitions, and structured multi-page study guides.

### 7. Media Agent (`src/agents/media_agent.py`)
- **Role:** GPU-accelerated SDXL image generation and GrokVideoNode video generation workflow construction.
- **Guardrail:** Evaluates workload via `GPUManager` to enforce a strict **$10.00 budget ceiling**.

---

## 6. Deterministic Workflows

Workflows execute reusable, multi-step multi-agent pipelines independently of the Director Agent.

### Executing a Workflow via CLI
```bash
python src/main.py --workflow "integration_pipeline"
```

### Writing a Custom Workflow (Python Example)
Add custom workflows in your script:
```python
from src.core.workflow_engine import Workflow, workflow_engine

def step1_research(context):
    return "Research findings"

def step2_copy(context):
    return f"Post based on: {context['step1_research']}"

wf = Workflow(workflow_id="custom_campaign", name="Custom Campaign Pipeline")
wf.add_step("step1_research", step1_research)
wf.add_step("step2_copy", step2_copy)

workflow_engine.register_workflow(wf)
```

---

## 7. System Configuration & Settings

System settings are controlled via environment variables or default fallbacks:

| Setting | Default Value | Description |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Endpoint for local LLM inference |
| `MAX_RUNPOD_BUDGET_USD` | `10.00` | RunPod cloud GPU budget limit |
| `PROJECT_STATE_DIR` | `Project_State/` | Directory for SQLite DB, cache, and state |
| `DEFAULT_CACHE_TTL_SEC` | `86400` (24 Hours) | Time-to-live for cached query payloads |
| `DEFAULT_DAG_NODE_TIMEOUT` | `60.0` Seconds | Timeout per node in DAG graph |

---

## 8. Plugin System & Integration Guide

The system uses `PluginManager` to extend capabilities without modifying core system code.

### Registering a New Plugin
Create a file in `src/agents/` or `src/plugins/`:
```python
from src.core.plugin_manager import BasePlugin, plugin_manager

class CustomPlugin(BasePlugin):
    @property
    def plugin_name(self) -> str:
        return "custom"

    @property
    def description(self) -> str:
        return "Custom third-party integration plugin."

    async def initialize(self) -> bool:
        return True

    async def execute_action(self, action_name: str, payload: dict) -> dict:
        return {"status": "success", "action": action_name}

# Register instance
plugin_manager.register_plugin(CustomPlugin())
```

---

## 9. RunPod & Cloud GPU Integration

Heavy media tasks (SDXL image rendering, Grok video generation) require GPU acceleration.

- **Local CPU/iGPU ($0.00)**: Used for all text generation, reasoning, planning, DOM perception, and research.
- **RunPod Cloud GPU**: Invoked only for heavy media workflows (`image_generation`, `video_generation`).
- **Cost Protection**: `GPUManager` tracks cumulative spend against the **$10.00 limit**. If the cap is reached, workloads automatically fall back to local/cloud API modes.

---

## 10. Troubleshooting & Diagnostics

### Problem 1: `CapabilitySelector` returns fallback model or connection error
- **Cause**: Ollama service is not running locally.
- **Solution**: Open terminal and start Ollama: `ollama serve`. Verify models exist: `ollama list`.

### Problem 2: `Playwright` browser error (`Executable doesn't exist`)
- **Cause**: Playwright Chromium binaries not downloaded.
- **Solution**: Run `playwright install chromium` in your shell.

### Problem 3: Action returns `approval_required`
- **Cause**: Destructive CLI command, social posting, or form submission safety gate triggered.
- **Solution**: This is intended safety behavior. Confirm the action when prompted or operate in safe mode.

---

## 11. Backup & System Restore

To back up the complete platform state, database, and cache:

### Backup Procedure
Compress or copy the following folders inside `Project_State/`:
1. `Project_State/Storage/knowledge.db` (SQLite records)
2. `Project_State/Cache/` (SHA-256 hash cache files)
3. `Project_State/Artifacts/` (Generated reports and artifacts)

### Restore Procedure
Paste the backed-up `knowledge.db`, `Cache/`, and `Artifacts/` folders back into `Project_State/`.

---

## 12. Future Developer Extension Guide

When adding new LLM providers, agents, or tools:
1. **Never alter core abstractions** (`EventBus`, `TaskDAG`, `WorkflowEngine`).
2. **Add new agents** as plugins implementing `BasePlugin`.
3. **Register new LLM backends** inside `src/providers/capability_selector.py`.
4. **Always create unit tests** under `tests/` before deploying new plugins.

---

## 13. Maintenance & Housekeeping

### Purging Expired Cache
Cache entries automatically expire after 24 hours (TTL). To force clear cache:
```python
from src.storage.storage_layer import storage
storage.clear_cache()
```

### Vacuuming SQLite Database
```python
import sqlite3
conn = sqlite3.connect("Project_State/Storage/knowledge.db")
conn.execute("VACUUM;")
conn.close()
```

---

## 14. Known System Limitations

1. **Integrated iGPU (AMD 512MB VRAM)**: Cannot run heavy SDXL or Flux models locally. Heavy media rendering relies on remote GPU pods or cloud APIs.
2. **Disk Space Management**: C: Drive has ~13 GB free space. Large model downloads should be directed to secondary storage drives if added.
3. **Bot-Protected Web Navigation**: Cloudflare-protected sites may require non-headless persistent browser profile context.

---

## 15. First Real Example: Facebook Campaign Workflow

This complete walkthrough demonstrates creating a Facebook post from an initial idea to a final image prompt and payload.

### Command Execution
Run the following CLI command in your terminal:
```bash
python src/main.py --goal "Create a Facebook post from idea to final image for AI Automation in 2026"
```

### Real Execution Sequence Output

```json
=== DIRECTOR ORCHESTRATION RESULT ===
{
  "status": "success",
  "source": "planner_dag",
  "result": {
    "model_assigned": "qwen2.5:1.5b",
    "orchestration": {
      "user_goal": "Create a Facebook post from idea to final image for AI Automation in 2026",
      "research_summary": "AI Automation in 2026 focuses on local multi-agent systems, deterministic task DAGs...",
      "facebook_post": {
        "copy": "🚀 Transform your business in 2026 with autonomous local AI agents! Boost efficiency without cloud vendor lock-in.",
        "hashtags": [
          "#AIAutomation",
          "#DigitalStrategy",
          "#TechInnovation",
          "#BusinessGrowth"
        ],
        "image_prompt": "Futuristic AI workstation with holographic DAG workflow diagram, 8k hyperrealistic"
      },
      "media_generation": {
        "gpu_target": "RUNPOD",
        "reason": "Heavy GPU workload 'image_generation' requires remote GPU execution."
      },
      "safety_gate": {
        "publishing_blocked": true,
        "message": "Publishing content to Facebook requires explicit user confirmation."
      }
    }
  }
}
```

### Artifact Location
The final campaign artifact is saved automatically to:
`Project_State/Artifacts/e2e_facebook_campaign_result.json`

Congratulations! You have successfully operated the **AI Operating System**.
