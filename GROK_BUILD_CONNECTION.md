# GUÍA EXACTA: CONECTAR GROK BUILD UI CON EL CEREBRO DM AUTONOMOUS

Esta guía explica paso a paso cómo usar **Grok Build UI** (o cualquier interfaz tipo ChatGPT, Cursor, Open WebUI, LibreChat, Bolt) como **cliente gráfico/interfaz**, utilizando **tu plataforma local como el cerebro autónomo completo con memoria persistente**.

---

## 1. Arquitectura de Conexión

```text
               GROK BUILD UI (Interfaz Gráfica)
                         |
           +-------------+-------------+
           |                           |
   OpenAI API Gateway            MCP SERVER
(http://localhost:8000/v1)   (http://localhost:8001)
           |                           |
           +-------------+-------------+
                         |
          DM AUTONOMOUS ORCHESTRATOR (Cerebro)
                         |
        +----------------+----------------+
        |                                 |
 SHORT-TERM MEMORY                 MEMORY BRAIN
 (Contexto de Sesión)          (Persistencia & Identidad)
        |                                 |
 Director Agent                      TaskDAG Engine
        |                                 |
 6 Agentes Especializados + Ollama Local + MCP Tools
```

---

## 2. Instrucciones de Inicio del Cerebro Local

Abre PowerShell en el workspace y ejecuta:

```powershell
.\start_platform.ps1
```

Este comando levantará:
- **API Gateway (REST + OpenAI Protocol):** `http://localhost:8000`
- **MCP Server (11 Tools):** `http://localhost:8001`
- **Modelos Locales Ollama:** Conectados (`qwen2.5:1.5b` & `qwen2.5:0.5b`)
- **Memoria Persistente:** Conectada (`Project_State/Memory/memory.db`)

---

## 3. Configuración en Grok Build UI

### OPCIÓN A: Conectar como API OpenAI Compatible (Recomendado para Chat)

En **Grok Build UI** (o cualquier cliente compatible con OpenAI):

1. Ve a **Settings -> Models -> Add Custom Provider (OpenAI Compatible)**.
2. Ingresa los siguientes valores:
   - **Base URL:** `http://localhost:8000/v1`
   - **API Key:** `dm-secret-key-v1`
   - **Model Name:** `dm-autonomous-brain`
3. Guarda la configuración y selecciona el modelo **`dm-autonomous-brain`**.

**¿Qué ocurre al enviar un mensaje desde Grok Build?**
- El mensaje llega a `http://localhost:8000/v1/chat/completions`.
- El cerebro inyecta automáticamente el perfil del usuario (`Daniel`) y la memoria de largo plazo relevante.
- Ejecuta los modelos Ollama y los agentes autónomos.
- Devuelve la respuesta en formato estándar de OpenAI y la guarda en la memoria.

---

### OPCIÓN B: Conectar como Servidor MCP (Herramientas Autónomas)

Si la interfaz Grok Build soporta **Model Context Protocol (MCP)**:

1. Ve a **Settings -> MCP Servers / Tools Integration -> Add MCP Server**.
2. Configura los parámetros:
   - **Name:** `DM-AI-Brain`
   - **Type:** `HTTP / SSE`
   - **Tools URL:** `http://localhost:8001/mcp/tools`
   - **Call URL:** `http://localhost:8001/mcp/call`
3. Grok Build habilitará automáticamente las **11 herramientas MCP del cerebro**:
   - `remember(content, category)`
   - `search_memory(query)`
   - `get_user_profile(user_id)`
   - `get_context(query)`
   - `run_agent(agent, task)`
   - `run_workflow(goal)`
   - `system_status()`
   - `list_agents()`
   - `get_artifacts()`

---

## 4. Ejemplos de Verificación con cURL

### Probar la API compatible con OpenAI desde la consola:
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dm-autonomous-brain",
    "messages": [
      {"role": "user", "content": "Hola, ¿cuáles son mis herramientas de automatización favoritas?"}
    ]
  }'
```

**Respuesta del cerebro (usando la memoria persistente de Daniel):**
> *"Hola Daniel. Tus herramientas de automatización preferidas son Ollama, n8n y CapCut..."*
