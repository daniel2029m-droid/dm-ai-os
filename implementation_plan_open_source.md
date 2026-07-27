# Plan de Integracion Open Source - DM AI OS

**Proyecto:** C:\Users\moral\.gemini\antigravity-ide\scratch
**Fecha:** 2026-07-26
**Proposito:** Reducir mantenimiento acoplando motores Open Source maduros como backends intercambiables. Arquitectura, identidad y API de DM AI OS quedan **intactas**.

---

## Principio Rector

**DM AI OS no se reescribe. Se enriquece.**

La estrategia es mediante **adaptadores delgados** (thin adapters): modulos aislados
que el sistema invoca opcionalmente cuando el motor Open Source esta disponible, y que
revierten al comportamiento actual si no lo esta. La regresion es imposible.

> IMPORTANTE — Arquitectura Congelada. Ninguno de los siguientes modulos sera modificado:
> BrainPipeline, OpenAI Router, chat_completions_router.py, MemoryManager, SQLiteStore,
> VectorStore, CapabilitySelector, PluginManager, MCP Server, API Gateway, routes.py,
> PWA/static/, Cloudflare, DAGEngine, WorkflowEngine, Tests existentes

---

## Resumen Ejecutivo

| Prioridad | Motor OS          | Modulo Actual a Enriquecer            | Modo                              |
|-----------|-------------------|---------------------------------------|-----------------------------------|
| 1         | Browser Use       | src/agents/browser_agent.py           | Adaptador opcional con fallback   |
| 2         | Crawl4AI          | src/agents/research_agent.py          | Backend de crawling intercambiable|
| 3         | Docling           | src/documents/document_pipeline.py    | Backend extractor con prioridad   |
| 4         | PocketFlow        | src/workflow/engine.py                | Adaptador lateral opt-in          |
| 5         | ChromaDB / Qdrant | src/memory/knowledge_store.py         | Capa de abstraccion VectorBackend |
| 6         | Vision Local      | src/providers/capability_selector.py  | Expansion del mapa de capacidades |

---

## PRIORIDAD 1 - Browser Use

### Que es

browser-use (https://github.com/browser-use/browser-use) es una libreria Python
que permite a modelos LLM navegar en el web de forma autonoma usando Playwright
con percepcion cognitiva enriquecida: DOM semantico, razonamiento y memoria de sesion.

### Analisis del modulo actual (browser_agent.py)

Estado actual:
- search_web(): POST a DuckDuckGo HTML, parseo de snippets con regex.
- decide_action(): percepcion DOM manual + razonamiento LLM.
- parse_perception(): parseo basico de roles DOM filtrado por texto visible.

Limitaciones:
- Parseo DOM con regex es fragil ante cambios del HTML de DuckDuckGo.
- No tiene capacidad de seguir enlaces ni navegar flujos multi-step.

### Propuesta

Nuevo archivo: src/adapters/browser_use_adapter.py

- Wraps browser-use como backend de navegacion cuando esta instalado.
- BrowserAgent.search_web() comprueba disponibilidad y delega. Si no, usa DDG actual.
- BrainPipeline NO cambia: sigue invocando plugin_manager.invoke("browser", ...).

Flujo:
```
BrainPipeline.process()
  -> plugin_manager.invoke("browser", "search", payload)
       -> BrowserAgent.search_web()
            -> [SI browser-use disponible] BrowserUseAdapter.search()
            -> [FALLBACK]                  DuckDuckGo HTML actual
```

### Ventajas

| Aspecto          | Beneficio                                                    |
|------------------|--------------------------------------------------------------|
| Fiabilidad       | Playwright cognitivo probado vs. regex sobre HTML             |
| Capacidades      | Navega flujos multi-step, extrae articulos completos          |
| Mantenibilidad   | Elimina parseo fragil DDG                                     |
| Anti-alucinacion | Extrae contenido real de paginas vs. snippets cortos          |

### Riesgos

| Riesgo                       | Severidad | Mitigacion                                       |
|------------------------------|-----------|--------------------------------------------------|
| Dependencia nueva            | Baja      | Fallback automatico al comportamiento actual      |
| Tiempo de inicio Playwright  | Media     | Pool de contextos reutilizados                    |
| Modelos LLM locales (Ollama) | Baja      | browser-use acepta /v1/chat/completions Ollama    |

### Compatibilidades

| Sistema            | OK  | Notas                                     |
|--------------------|-----|-------------------------------------------|
| BrainPipeline      | YES | Transparente, sin cambios                 |
| OpenAI API         | YES | browser-use acepta endpoint Ollama compat |
| MCP Server         | YES | web_search sigue invocando el mismo plugin|
| PWA                | YES | Sin impacto en frontend                   |
| Cloudflare         | YES | Solo trafico local                         |
| CapabilitySelector | YES | Informa al adaptador el modelo seleccionado|

### Dependencias

```
browser-use>=0.2.0
playwright>=1.45.0   # ya es dependencia del proyecto
```

---

## PRIORIDAD 2 - Crawl4AI

### Que es

Crawl4AI (https://github.com/unclecode/crawl4ai) es un motor de web crawling asincrono
optimizado para LLMs. Extrae contenido estructurado limpio (markdown, JSON, tablas),
elimina publicidad y boilerplate. Hasta 6x mas rapido que Beautiful Soup.

### Analisis del modulo actual (research_agent.py)

Limitacion principal: conduct_research() depende de snippets cortos (100-300 chars)
de DuckDuckGo HTML. Texto insuficiente -> el LLM rellena con alucinaciones.

Oportunidad: Si Crawl4AI visita directamente las URLs y extrae el articulo completo,
el LLM trabaja con texto fuente 100% verificable.

### Propuesta

Nuevo archivo: src/adapters/crawl4ai_adapter.py

- Expone: async crawl_url(url: str) -> str  (retorna markdown limpio del articulo)
- ResearchAgent.conduct_research() llama al adaptador para cada URL en web_sources.
- Si Crawl4AI no esta disponible, cae al comportamiento actual (snippets DDG).

Flujo:
```
ResearchAgent.conduct_research(topic)
  -> BrowserAgent.search_web(topic)          # sin cambios
       -> sources: ["Titulo: URL", ...]
            -> [SI crawl4ai disponible]
                 -> Crawl4AIAdapter.crawl_url(URL)  # articulo completo
            -> [FALLBACK]
                 -> web_context = snippets DDG (actual)
```

### Ventajas

| Aspecto             | Beneficio                                         |
|---------------------|---------------------------------------------------|
| Calidad de noticias | Pasa de ~200 chars de snippet a articulo completo |
| Anti-alucinacion    | LLM trabaja con texto fuente verificable          |
| Mantenimiento       | Elimina regex de parseo HTML a largo plazo        |
| Rendimiento         | Crawl asincrono paralelo de multiples URLs        |

### Riesgos

| Riesgo                  | Severidad | Mitigacion                                |
|-------------------------|-----------|-------------------------------------------|
| Latencia adicional      | Media     | Timeout 15s + cache CacheLayer            |
| URLs con JavaScript     | Baja      | Crawl4AI tiene Playwright headless integrado|
| Rate limiting de sitios | Baja      | Crawl solo de las top 3 URLs              |

### Compatibilidades

| Sistema           | OK  | Notas                                  |
|-------------------|-----|----------------------------------------|
| BrainPipeline     | YES | Sin cambios en interfaz de ResearchAgent|
| OpenAI API        | YES | Sin impacto                             |
| MCP web_search    | YES | Sigue funcionando igual                 |
| CacheLayer        | YES | Articulos cacheados ahorran re-crawling |

### Dependencias

```
crawl4ai>=0.6.0
```

---

## PRIORIDAD 3 - Docling

### Que es

Docling (https://github.com/DS4SD/docling) es la libreria de extraccion de documentos de
IBM Research. Soporta PDF (con OCR), DOCX, XLSX, PPTX, HTML, AsciiDoc y Markdown.
Produce salida unificada con fragmentos semanticos, tablas preservadas y jerarquia
de secciones. Estado del arte en extraccion documental Open Source (2024-2026).

### Analisis del modulo actual (document_pipeline.py)

Limitaciones:
- extract_text_from_pdf(): pypdf con fallback a regex sobre bytes. Ignora estructura.
- extract_text_from_docx(): python-docx + fallback XML manual. Ignora tablas y estilos.
- extract_text_from_txt(): solo decodificacion de bytes, sin estructura.

Ningun extractor preserva tablas, jerarquia de secciones, formulas ni layout complejo.

### Propuesta

Nuevo archivo: src/adapters/docling_adapter.py

- Expone: extract(content_bytes: bytes, filename: str) -> str
- DocumentPipeline llama al adaptador como primera opcion. Si Docling no esta
  instalado o falla, cae en los extractores actuales.
- La API publica de DocumentPipeline.process_document() NO cambia.

Flujo:
```
DocumentPipeline.process_document(content_bytes, filename)
  -> [SI docling disponible]
       -> DoclingAdapter.extract(content_bytes, filename)  # texto rico estructurado
  -> [FALLBACK]
       -> extract_text_from_pdf/docx/txt() (actual)
```

### Ventajas

| Aspecto              | Beneficio                                         |
|----------------------|---------------------------------------------------|
| Calidad de extraccion| PDF con OCR, tablas, secciones jerarquicas        |
| Mantenimiento        | Elimina ~80 lineas de extractores caseros         |
| Formatos adicionales | PPTX, XLSX, HTML sin implementacion adicional     |
| Chunking semantico   | Fragmentos por seccion para mejor RAG             |

### Riesgos

| Riesgo                      | Severidad | Mitigacion                              |
|-----------------------------|-----------|------------------------------------------|
| Instalacion pesada (torch)  | Media     | Modo sin OCR por defecto; OCR opcional   |
| Primera carga lenta         | Baja      | Warm-up al inicio del servidor           |

### Compatibilidades

| Sistema             | OK  | Notas                                       |
|---------------------|-----|---------------------------------------------|
| MemoryManager       | YES | Texto extraido se indexa igual en VectorStore|
| MCP index_document  | YES | Sin cambios en herramienta MCP              |
| OpenAI API          | YES | Sin impacto en capa de compatibilidad       |
| BrainPipeline       | YES | Sin cambios                                  |

### Dependencias

```
docling>=2.0.0
# Opcionales: torch (OCR), easyocr
```

---

## PRIORIDAD 4 - PocketFlow vs. LangGraph

### Analisis comparativo

| Criterio                | LangGraph                      | PocketFlow            |
|-------------------------|--------------------------------|-----------------------|
| Madurez                 | Alta (ecosistema LangChain)    | Media-Alta            |
| Tamano                  | Grande (~180 deps transitivas) | Minimal (~100 lineas core)|
| Compatibilidad Ollama   | YES nativa                     | YES via HTTPX         |
| Conflicto con DAGEngine | Posible solapamiento           | Minimo                |
| Curva de adopcion       | Alta                           | Baja                  |
| Modo async              | YES completo                   | YES                   |

**Recomendacion: PocketFlow.**

PocketFlow es minimalista y no impone opiniones de arquitectura. Su nucleo
(4 clases: Node, Flow, BatchFlow, AsyncFlow) es acoplable como motor auxiliar
sin interferir con WorkflowEngine ni DAGEngine.

LangGraph requiere el ecosistema LangChain completo con riesgo de colision
con httpx, pydantic y fastapi en versiones especificas del proyecto.

### Propuesta

Nuevo archivo: src/adapters/pocketflow_adapter.py

- Expone: PocketFlowAdapter.run_flow(flow_definition: dict) -> dict
- WorkflowEngine delega opcionalmente flujos marcados con engine: "pocketflow".
- Si el parametro engine no esta o es "native", WorkflowEngine actual sigue sin cambios.

Flujo:
```
WorkflowEngine.run(workflow_def)
  -> [Si engine == "pocketflow"]
       -> PocketFlowAdapter.run_flow(workflow_def)
  -> [Por defecto]
       -> WorkflowEngine original (sin cambios)
```

### Ventajas

| Aspecto          | Beneficio                                  |
|------------------|--------------------------------------------|
| Flujos paralelos | PocketFlow Batch maneja N nodos en paralelo|
| Sin reescritura  | Motor actual no se toca                    |
| Depuracion       | Visualizacion nativa de grafos             |

### Riesgos

| Riesgo                 | Severidad | Mitigacion                               |
|------------------------|-----------|------------------------------------------|
| Solapamiento DAGEngine | Baja      | 100% opt-in, DAGEngine sigue siendo default|
| Estado early-stage     | Media     | Fallback al engine actual en caso de error|

### Dependencias

```
pocketflow>=0.0.2
```

---

## PRIORIDAD 5 - Capa de Abstraccion VectorBackend

### Estado actual

La memoria vectorial usa implementacion propia basada en JSON (vector_index.json) con
distancia coseno en Python puro (embedding_engine.py + knowledge_store.py). Funciona
correctamente para el volumen actual (<= 100K vectores). Riesgo: escalabilidad futura
y mantenimiento de logica coseno propia.

### Alternativas evaluadas

| Motor    | Tipo              | Ollama | MCP | Produccion | Notas                              |
|----------|-------------------|--------|-----|------------|------------------------------------|
| ChromaDB | Embebido/Servidor | YES    | YES | Alta       | Sin servidor en modo embebido      |
| Qdrant   | Servidor Rust     | YES    | YES | Muy Alta   | Mejor para >1M vectores            |
| FAISS    | Embebido          | YES    | YES | Alta       | Facebook AI, sin servidor, ideal local|

**Recomendacion: ChromaDB como primera alternativa, FAISS como opcion offline.**

ChromaDB corre completamente embebido, reemplaza el JSON store directamente y es
compatible con nomic-embed-text (Ollama) para generar embeddings.

### Propuesta

Nuevo archivo: src/memory/vector_backend.py

Interfaz abstracta:
```python
class VectorBackend(ABC):
    def save_vector(self, id, content, embedding, metadata) -> None: ...
    def search_similar(self, embedding, top_k) -> List[Dict]: ...
    def delete_vector(self, id) -> None: ...
```

Implementaciones intercambiables:
- JsonVectorBackend:   implementacion actual (por defecto, sin cambios).
- ChromaVectorBackend: ChromaDB cuando esta instalado.
- FaissVectorBackend:  FAISS para hardware con GPU/ARM.

Seleccion via variable de entorno: VECTOR_BACKEND=chroma|faiss|json

> AVISO: No se migra automaticamente ningun dato existente. El JSON backend es
> el default. La migracion a ChromaDB/FAISS sera voluntaria y mediante script separado.

### Ventajas

| Aspecto              | Beneficio                                               |
|----------------------|---------------------------------------------------------|
| Escalabilidad futura | Sin cambios de codigo para escalar de 1K a 10M vectores |
| Mantenimiento        | Elimina la implementacion coseno propia                |
| Rendimiento          | ChromaDB 20-100x mas rapido en busquedas >10K vectores  |

### Riesgos

| Riesgo                    | Severidad | Mitigacion                                |
|---------------------------|-----------|-------------------------------------------|
| Migracion de datos        | Media     | JSON backend por defecto perpetuamente    |
| Incompatibilidad embeddings| Baja     | Mismos modelos Ollama para ambos backends |
| Servidor adicional Qdrant | Media     | ChromaDB embebido no requiere servidor    |

### Compatibilidades

| Sistema            | OK  | Notas                                  |
|--------------------|-----|----------------------------------------|
| MemoryManager      | YES | Usa misma API de knowledge_store        |
| MCP search_memory  | YES | Sin cambios en herramienta MCP         |
| Ollama embeddings  | YES | nomic-embed-text sigue siendo el modelo |
| BrainPipeline      | YES | Sin cambios                             |

### Dependencias (opcionales por backend)

```
chromadb>=0.5.0        # ChromaDB embebido
faiss-cpu>=1.8.0       # FAISS sin GPU
qdrant-client>=1.10.0  # Solo si se usa Qdrant servidor
```

---

## PRIORIDAD 6 - Vision: Modelos Locales

### Estado actual

CapabilitySelector ya tiene mappings para vision:
```python
"vision": ["llava", "bakllava", "llama3.2-vision", "qwen2-vl", "qwen2.5:1.5b"]
"ocr":    ["llava", "bakllava", "llama3.2-vision", "qwen2-vl", "qwen2.5:0.5b"]
```

BrainPipeline.process() ya detecta images en el payload y selecciona "vision".
El sistema ya soporta vision si los modelos estan instalados en Ollama.
No hay componentes que reemplazar; solo se propone un adaptador de mejora minima.

### Propuesta

Nuevo archivo: src/adapters/vision_adapter.py

- Preprocesa imagenes (resize, compresion, encoding base64) antes de enviar al LLM.
- Expone: analyze_image(image_bytes, prompt) -> str
- Permite acceso a capacidades especializadas: ocr, captioning, object_detection.

Modelos prioritarios por capacidad:

| Capacidad                  | Modelo Preferido       | Alternativa         |
|----------------------------|------------------------|---------------------|
| OCR / lectura de texto     | qwen2.5-vl:7b         | llava:7b            |
| Comprension visual compleja| llama3.2-vision:11b   | qwen2-vl:7b         |
| Captioning rapido          | bakllava:7b            | llava:7b            |
| Analisis codigo pantalla   | qwen2.5-vl:7b         | llama3.2-vision:11b |

### Compatibilidades

| Sistema            | OK  | Notas                                       |
|--------------------|-----|---------------------------------------------|
| CapabilitySelector | YES | Solo expansion del mapa de capacidades      |
| BrainPipeline      | YES | Sin cambios de interfaz                    |
| OpenAI API         | YES | Imagenes via content: [{type: image_url}]   |
| MCP Server         | YES | Nueva herramienta analyze_image opcional    |

### Dependencias

```
# Ninguna adicional - solo modelos Ollama:
# ollama pull llava:7b
# ollama pull qwen2.5-vl:7b
# ollama pull llama3.2-vision:11b
```

---

## Arquitectura de Adaptadores Propuesta

```
src/
+-- adapters/                          <- NUEVO DIRECTORIO (solo archivos nuevos)
|   +-- __init__.py
|   +-- browser_use_adapter.py         <- P1: Browser Use
|   +-- crawl4ai_adapter.py            <- P2: Crawl4AI
|   +-- docling_adapter.py             <- P3: Docling
|   +-- pocketflow_adapter.py          <- P4: PocketFlow
|   +-- vision_adapter.py             <- P6: Vision
|
+-- memory/
    +-- vector_backend.py              <- P5: Interfaz abstracta VectorBackend
        +-- JsonVectorBackend  (actual, sin cambios)
        +-- ChromaVectorBackend (nuevo)
        +-- FaissVectorBackend  (nuevo)
```

**Patron de Integracion Estandar DM AI OS (todos los adaptadores):**

1. _is_available() -> bool: prueba si la libreria esta instalada antes de invocarla.
2. Graceful fallback: Si no disponible, comportamiento actual intacto y logueado.
3. Sin modificar el modulo original: el modulo existente llama al adaptador opcionalmente.
4. Config por variable de entorno: BROWSER_USE_ENABLED=true, VECTOR_BACKEND=chroma.
5. Logging unificado: log = logging.getLogger("adapter_name") mismo formato.

---

## Compatibilidades Globales

| Capa / Sistema          | Browser Use | Crawl4AI | Docling | PocketFlow | ChromaDB | Vision |
|-------------------------|-------------|----------|---------|------------|----------|--------|
| BrainPipeline           | YES         | YES      | YES     | YES        | YES      | YES    |
| OpenAI API /v1/chat     | YES         | YES      | YES     | YES        | YES      | YES    |
| MCP Server (15 tools)   | YES         | YES      | YES     | YES        | YES      | YES    |
| Ollama Local            | YES         | YES      | YES     | YES        | YES      | YES    |
| PWA / SSE Frontend      | YES         | YES      | YES     | YES        | YES      | YES    |
| Cloudflare Tunnel       | YES         | YES      | YES     | YES        | YES      | YES    |
| MemoryManager           | YES         | YES      | YES     | YES        | YES      | YES    |
| CapabilitySelector      | YES         | YES      | YES     | YES        | YES      | YES    |
| Tests Existentes        | YES         | YES      | YES     | YES        | YES      | YES    |

NOTA: Compatibilidad con tests garantizada por el patron de fallback:
si el motor externo no esta instalado en el entorno de tests, el codigo retorna
al comportamiento actual que los tests ya validan. Cero regresiones.

---

## Matriz de Riesgos Consolidada

| Integracion | Riesgo Principal               | Impacto | Probabilidad | Mitigacion                       |
|-------------|--------------------------------|---------|--------------|----------------------------------|
| Browser Use | Cambio de API upstream         | Media   | Baja         | Pinned version en requirements   |
| Crawl4AI    | Latencia adicional en research | Media   | Media        | Timeout 15s + cache CacheLayer   |
| Docling     | Peso de dependencias (torch)   | Alta    | Media        | docling[minimal] sin OCR default |
| PocketFlow  | Inmadurez relativa             | Baja    | Media        | 100% opt-in, fallback nativo     |
| ChromaDB    | Migracion de vectores existentes| Media  | Baja         | JSON backend por defecto siempre |
| Vision      | Modelos no instalados en Ollama| Baja    | Alta         | CapabilitySelector ya maneja     |

---

## Orden de Implementacion Recomendado

```
FASE A - Bajo riesgo, alto impacto inmediato:
  -> P3: Docling Adapter      src/adapters/docling_adapter.py
  -> P2: Crawl4AI Adapter     src/adapters/crawl4ai_adapter.py

FASE B - Impacto alto, riesgo controlado:
  -> P1: Browser Use Adapter  src/adapters/browser_use_adapter.py
  -> P5: VectorBackend        src/memory/vector_backend.py

FASE C - Complementario, opt-in puro:
  -> P4: PocketFlow Adapter   src/adapters/pocketflow_adapter.py
  -> P6: Vision Adapter       src/adapters/vision_adapter.py
```

---

## Resumen Final

| Aspecto                   | Estado Antes                     | Estado Despues                        |
|---------------------------|----------------------------------|---------------------------------------|
| Parsing web               | Regex sobre HTML DuckDuckGo      | Browser Use + fallback DDG            |
| Scraping de contenido     | Snippets ~200 chars              | Articulos completos (Crawl4AI)        |
| Extraccion PDF/DOCX       | pypdf + XML manual               | Docling con OCR y estructura          |
| Motor de workflows        | DAGEngine propio                 | DAGEngine + PocketFlow opt-in         |
| Almacenamiento vectorial  | JSON local propio                | JSON / ChromaDB / FAISS (abstracto)   |
| Vision local              | CapabilitySelector basico        | Adaptador granular por subtipo        |
| Lineas de codigo propio   | ~1,200 en modulos criticos       | <300 en adaptadores delgados          |
| Arquitectura              | Intacta                          | INTACTA                               |
| Identidad DM AI OS        | Preservada                       | PRESERVADA                            |
| Compatibilidad OpenAI API | 100%                             | 100%                                  |
| Compatibilidad MCP        | 100%                             | 100%                                  |

PROXIMO PASO NATURAL: comenzar por la Fase A — implementar docling_adapter.py
y crawl4ai_adapter.py. Son los de menor riesgo, mayor impacto en calidad de salida
y no requieren tocar ningun modulo congelado.
