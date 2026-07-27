# DECISIONS_LOG.md
**DM AI OS — Registro de Decisiones Tecnicas**
**Ultima Actualizacion:** 2026-07-26T18:30:00-03:00

> Las decisiones cerradas son FINALES. Nunca reabrir sin razon tecnica documentada.

---

## Decisiones Heredadas (Sesiones 1-4)

### D-001 — Sistema de Estado del Proyecto
**Estado:** CERRADA | Toda la memoria del proyecto vive en /Project_State/ + documentos maestros raiz.

### D-002 — Principio de Maxima Reutilizacion
**Estado:** CERRADA | Reutilizar codigo existente antes de escribir codigo nuevo.

### D-003 — Principio de Recursos y Presupuesto
**Estado:** CERRADA | Minimizar RAM, CPU, GPU, disco, tokens y creditos RunPod.

### D-004 — Arquitectura Provider-Agnostica
**Estado:** CERRADA | Todos los providers abstraidos detras de interfaces uniformes.

### D-005 — Scoping Razonamiento vs. Ejecucion
**Estado:** CERRADA | Modelos locales para razonamiento; RunPod exclusivamente para GPU/media.

### D-006 — Seguridad y Gestion de Secretos
**Estado:** CERRADA | Secretos en variables de entorno / Credential Manager.

### D-007 — Selector de Modelos Dinamico
**Estado:** CERRADA | Routing basado en capability (task_type) + cascade de prioridad.

### D-008 — Integracion Context Manager + Scheduler
**Estado:** CERRADA | Context Manager controla estado/memoria; Scheduler controla colas async.

### D-009 — Storage Layer Unificada
**Estado:** CERRADA | StorageManager envuelve SQLite, Vector DB, Filesystem y Cache SHA-256.

### D-010 — EventBus + GPU Manager
**Estado:** CERRADA | Comunicacion event-driven pub/sub; GPU Manager controla gasto RunPod.

### D-011 — Workflow Engine + Director
**Estado:** CERRADA | Director es liviano (dispara workflows); WorkflowEngine ejecuta tareas multi-step.

### D-012 — Plugin Manager
**Estado:** CERRADA | Integraciones como plugins sin alterar el nucleo.

### D-013 — DAG Execution
**Estado:** CERRADA | Tareas estructuradas como DAGs para ejecucion paralela.

### D-014 — CONGELAMIENTO DE ARQUITECTURA + TDD
**Estado:** CERRADA | Arquitectura congelada. TDD: Test -> Implementar -> Verificar -> Estado -> Siguiente.

---

## Decisiones de Fase A/B/C (Open Source Integration)

### D-015 — Patron de Adaptadores Delgados
**Estado:** CERRADA
**Fecha:** 2026-07-26
**Decision:** Toda nueva capacidad Open Source se integra mediante adaptadores delgados en src/adapters/.
El patron estandar es: _is_available() check -> graceful fallback -> env var config -> unified logging.
El modulo original siempre tiene fallback al comportamiento actual si el adaptador no esta disponible.
**Razon:** Cero regresiones garantizadas. Tests existentes nunca fallan por falta de dependencias opcionales.

### D-016 — Prioridad Open Source con Fallback
**Estado:** CERRADA
**Fecha:** 2026-07-26
**Decision:** Usar proyectos Open Source maduros como backends intercambiables.
Orden de prioridad: Docling (P3) -> Crawl4AI (P2) -> Browser Use (P1) -> VectorBackend (P5) -> PocketFlow (P4) -> Vision (P6).
Nunca reinventar soluciones existentes. Siempre verificar disponibilidad de OS antes de escribir codigo.

### D-017 — Docling en Modo Minimal por Defecto
**Estado:** CERRADA
**Fecha:** 2026-07-26
**Decision:** Docling se integra sin OCR por defecto (docling[minimal]) para evitar dependencia de torch.
OCR se activa opcionalmente con DOCLING_OCR_ENABLED=true en .env.
**Razon:** torch es pesado (>2GB). La mayoria de documentos no requieren OCR.

### D-018 — Crawl4AI con Timeout y Cache
**Estado:** CERRADA
**Fecha:** 2026-07-26
**Decision:** Crawl4AI usa timeout de 15 segundos por URL. Solo crawlea las top 3 URLs.
Los articulos crawleados se cachean via CacheLayer existente para evitar re-crawling.
**Razon:** Balance entre calidad de contenido y latencia aceptable para el usuario.

### D-019 — JSON Vector Backend por Defecto Perpetuamente
**Estado:** CERRADA
**Fecha:** 2026-07-26
**Decision:** El backend vectorial JSON actual es el default permanente. ChromaDB/FAISS son opt-in via VECTOR_BACKEND env var.
No se migran datos automaticamente. Script de migracion separado cuando el usuario lo solicite.
**Razon:** No romper la instalacion existente. La abstraccion VectorBackend es para escalabilidad futura.
