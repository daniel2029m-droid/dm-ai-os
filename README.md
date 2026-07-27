# AI Operating System (AI OS)
**Version 1.0.0 — Production Release**

A provider-agnostic, plugin-driven, DAG-based multi-agent AI Operating System designed for local intelligence, web & OS automation, content creation, and GPU media rendering under a strict budget ceiling.

---

## Key Features
- **Lightweight Director Agent**: Goal orchestrator that delegates tasks without carrying business logic.
- **Capability-Based Dynamic Model Selector**: Automatically probes local Ollama backends (`qwen2.5:1.5b` / `0.5b`) and routes tasks by capability.
- **TaskDAG Engine**: Executes parallel task graphs concurrently with topological ordering and per-node timeout protection.
- **Deterministic Workflow Engine**: Runs step-by-step multi-agent pipelines independently.
- **SHA-256 Cache Layer**: Reduces repeat query response times to **0.27 ms** with zero token consumption.
- **Unified Storage Layer**: SQLite database (`knowledge.db`) + SHA-256 Cache + Filesystem Artifacts.
- **GPUManager & MediaAgent**: Evaluates heavy workloads (SDXL / GrokVideoNode) and enforces a strict **$10 budget limit**.
- **Human-in-the-Loop Safety Gates**: Automatic security blocking for destructive CLI actions (`rmdir`, `del`), social publishing (`FacebookAgent`), and web form submissions (`BrowserAgent`).

---

## Quickstart

### 1. Installation
Ensure Python 3.10+ and Ollama are installed:
```bash
pip install -r requirements.txt
playwright install chromium
ollama pull qwen2.5:1.5b
ollama pull qwen2.5:0.5b
```

### 2. Operational Commands

#### System Status
```bash
python src/main.py --system-status
```

#### List Registered Plugins
```bash
python src/main.py --list-plugins
```

#### Execute a Goal
```bash
python src/main.py --goal "Research AI automation trends in 2026"
```

#### Invoke a Direct Plugin Action
```bash
python src/main.py --plugin computer --action sys_info
```

#### Run Automated Test Suites
```bash
python tests/test_phase3_integration.py
python tests/test_phase4_real_validation.py
python tests/test_phase4_e2e_workflow.py
```

---

## Project Structure
- **`src/`**: Python source code (`main.py`, `agents/`, `core/`, `providers/`, `storage/`).
- **`tests/`**: Unit, integration, acceptance, and validation test suites.
- **`config/`**: JSON system settings.
- **`logs/`**: Log files directory.
- **`Project_State/`**: SQLite database, SHA-256 cache files, artifacts, and audits.
- **`USER_MANUAL.md`**: Complete 15-section operational user manual.

---

## License
[MIT License](LICENSE)
