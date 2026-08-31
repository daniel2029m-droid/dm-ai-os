# 🧠 DM AI OS v1.5.2 — Antigravity Autonomous Orchestrator

## 1. Arquitectura General

```text
📱 iPhone (PWA / Safari)
    │
    │ HTTPS (Cloudflare Tunnel)
    ▼
DM AI OS API Gateway (Puerto 8000)
    │
    │ /api/v1/antigravity/orchestrate
    ▼
Antigravity Orchestrator Engine
    │
    ├── 1. Capabilities Discovery (Health Check, Sockets, Model)
    ├── 2. Auto Routing (Antigravity Priority 1 -> Ollama Direct Fallback)
    ├── 3. Multi-Step Task Planner (Task Decomposition, Step Graph)
    ├── 4. Security Gating (READ_ONLY, APPROVAL_REQUIRED, AUTONOMOUS)
    ├── 5. Physical Post-Action Verifier (Disk existence, SHA256 hashes)
    └── 6. Audit Telemetry Log (SQLite persistent audit store)
```

## 2. Componentes del Orquestador

* **`AntigravityAgentProvider`:** Ejecuta `google.antigravity.Agent` (v0.1.15) mediante `LocalOpenAIAgentConfig` conectado a Ollama local (`127.0.0.1:11434/v1`).
* **`OllamaDirectProvider`:** Motor de fallback seguro ante degradación o indisponibilidad del Agent Runtime.
* **`MultiStepPlanner`:** Descompone instrucciones de alto nivel en planes estructurados con estados individuales por paso (`PENDING`, `RUNNING`, `COMPLETED`, `AWAITING_APPROVAL`, `FAILED`).
* **`PhysicalVerifier`:** Comprobador independiente que valida en disco el resultado físico de cada acción reportada.
