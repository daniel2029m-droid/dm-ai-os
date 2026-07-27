# ARCHITECTURE_INDEX.md
**DM AI OS — Indice de Arquitectura**
**Ultima Actualizacion:** 2026-07-26T23:11:00-03:00

---

## Principio Absoluto: ARQUITECTURA CONGELADA

El nucleo NO se modifica. Solo se agregan ADAPTADORES en src/adapters/.

---

## Estructura de Directorios

`
scratch/
+-- src/
|   +-- __init__.py
|   +-- main.py                        # CLI Entry Point
|   +-- grok_validation.py             # Grok integration validator
|   +-- adapters/                      [NUEVO - Fases A/B/C/15/17]
|   |   +-- __init__.py
|   |   +-- docling_adapter.py         # P3: Extraccion estructurada docs
|   |   +-- crawl4ai_adapter.py        # P2: Web crawling para LLMs
|   |   +-- browser_use_adapter.py     # P1: Navegacion cognitiva
|   |   +-- pocketflow_adapter.py      # P4: Motor de workflows
|   |   +-- vision_adapter.py          # P6: Vision local
|   |   +-- tenant_isolation_adapter.py# Fase 15: SaaS Isolation completa
|   |   +-- learning_engine.py         # Fase 17: Aprendizaje continuo
|   +-- autonomy/                      [NUEVO - Fase 18]
|   |   +-- __init__.py
|   |   +-- cognitive_scheduler.py     # Scheduler cognitivo autonomo
|   +-- commercial/                    [NUEVO - Fase 19]
|   |   +-- __init__.py
|   |   +-- assistant_factory.py       # Plataforma comercial 22 templates
|   +-- agents/                        [CONGELADO]
|   |   +-- browser_agent.py           # Playwright + DuckDuckGo + Crawl4AI
|   |   +-- computer_agent.py          # File system operations
|   |   +-- director.py                # Lightweight orchestrator
|   |   +-- facebook_agent.py          # Social media agent
|   |   +-- media_agent.py             # RunPod GPU + Grok media
|   |   +-- research_agent.py          # Research + Crawl4AI adapter
|   |   +-- university_agent.py        # Academic study agent
|   +-- api/                           [CONGELADO]
|   |   +-- routes.py                  # FastAPI API Gateway
|   |   +-- chat_completions_router.py # OpenAI-compatible /v1/chat/completions
|   +-- core/                          [CONGELADO]
|   |   +-- brain_pipeline.py          # BrainPipeline — NUCLEO CENTRAL
|   |   +-- dag_engine.py              # DAGEngine — ejecucion paralela
|   |   +-- event_bus.py               # EventBus pub/sub
|   |   +-- plugin_manager.py          # PluginManager — registro de agentes
|   |   +-- scheduler.py               # Scheduler — cola de tareas
|   |   +-- workflow_engine.py         # WorkflowEngine multi-step
|   +-- documents/                     [CONGELADO — API publica inalterada]
|   |   +-- document_pipeline.py       # DocumentPipeline + Docling adapter
|   +-- mcp/                           [CONGELADO]
|   |   +-- server.py                  # MCP Server (15 tools)
|   |   +-- tools.py                   # Herramientas MCP
|   +-- memory/                        [CONGELADO — agregar vector_backend.py en Fase B]
|   |   +-- embedding_engine.py        # Embeddings locales Ollama
|   |   +-- knowledge_store.py         # JSON VectorStore
|   |   +-- memory_manager.py          # MemoryManager unificado
|   |   +-- vector_backend.py          # [PENDIENTE Fase B] Capa abstracta
|   +-- providers/                     [CONGELADO]
|   |   +-- capability_selector.py     # CapabilityModelSelector
|   |   +-- gpu_manager.py             # GPU Manager RunPod
|   +-- storage/                       [CONGELADO]
|   |   +-- storage_layer.py           # SQLite + SHA256 Cache + Filesystem
|   +-- users/                         [CONGELADO]
|       +-- user_manager.py            # Aislamiento por usuario
+-- tests/                             [NUNCA BORRAR]
|   +-- test_browser_agent.py
|   +-- test_computer_agent.py
|   +-- test_research_agent.py
|   +-- test_facebook_agent.py
|   +-- test_university_agent.py
|   +-- test_media_agent.py
|   +-- test_phase3_integration.py     # 11/11 PASS
|   +-- test_phase4_real_validation.py # 15/16 VERIFIED
|   +-- test_adapters_phase_a.py       # NUEVO Fase A
+-- Project_State/                     # Memoria del proyecto
+-- docs/                              # Documentacion
+-- PROJECT_MASTER_STATE.md            # Estado maestro (este proyecto)
+-- ARCHITECTURE_INDEX.md              # Este archivo
+-- DECISIONS_LOG.md                   # Decisiones tecnicas
+-- OPEN_SOURCE_INTEGRATION_STATUS.md  # Estado integraciones OS
+-- BACKLOG.md                         # Trabajo pendiente priorizado
`

---

## Flujo de Datos Principal

`
Usuario/iPhone
    |
    v
Cloudflare Tunnel
    |
    v
API Gateway (FastAPI routes.py)
    |
    v
chat_completions_router.py (OpenAI-compatible)
    |
    v
BrainPipeline.process()
    |
    +---> CapabilitySelector (elige modelo LLM)
    +---> PluginManager.invoke(agent, action, payload)
    |         |
    |         +---> BrowserAgent    --> [Crawl4AI Adapter] --> [Browser Use Adapter]
    |         +---> ResearchAgent   --> [Crawl4AI Adapter]
    |         +---> ComputerAgent
    |         +---> FacebookAgent
    |         +---> MediaAgent      --> RunPod GPU
    |         +---> UniversityAgent
    |
    +---> MemoryManager (SQLite + VectorStore)
    |         |
    |         +---> EmbeddingEngine (Ollama nomic-embed-text)
    |         +---> KnowledgeStore (JSON / [ChromaDB Fase B])
    |
    +---> WorkflowEngine / DAGEngine
    |
    v
EventBus (pub/sub)
    |
    v
Scheduler (async task queue)
`

---

## Patron de Adaptadores (Estandar DM AI OS)

`python
class XAdapter:
    @staticmethod
    def _is_available() -> bool:
        """Verifica si la libreria esta instalada."""
        try:
            import x_library
            return True
        except ImportError:
            return False

    def action(self, ...):
        if not self._is_available():
            # Fallback al comportamiento actual
            return None
        # Logica open source
        ...
`

Reglas:
1. _is_available() — verifica disponibilidad antes de invocar
2. Graceful fallback — si no disponible, retorna None y el caller usa comportamiento actual
3. Sin modificar modulos congelados — solo el caller agrega la llamada opcional
4. Config por env var — DOCLING_ENABLED, CRAWL4AI_ENABLED, BROWSER_USE_ENABLED, VECTOR_BACKEND
5. Logging unificado — logging.getLogger("adapter_name")

---

## Modulos Congelados (NUNCA MODIFICAR)

- src/core/brain_pipeline.py
- src/core/dag_engine.py
- src/core/event_bus.py
- src/core/plugin_manager.py
- src/core/scheduler.py
- src/core/workflow_engine.py
- src/api/routes.py
- src/api/chat_completions_router.py
- src/memory/embedding_engine.py
- src/memory/knowledge_store.py
- src/memory/memory_manager.py
- src/mcp/server.py
- src/providers/gpu_manager.py
- src/storage/storage_layer.py
- src/users/user_manager.py
- src/agents/director.py
- src/agents/computer_agent.py
- src/agents/facebook_agent.py
- src/agents/media_agent.py
- src/agents/university_agent.py
- Todos los tests existentes
