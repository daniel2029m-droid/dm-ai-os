# 🌟 DM AI OS v1.5.2-LTS: Radiografía Maestra y Documentación del Sistema

> **Estado del Sistema:** `FROZEN (CONGELADO Y 100% OPERATIVO)`  
> **Fecha de Instantánea:** `2026-09-01`  
> **Checksum de Integridad:** `CHECKSUMS_SHA256.txt` verificado.

---

## 1. 🏗️ Arquitectura Completa del Sistema

```text
📱 CLIENTE MÓVIL / PWA (https://ai.dmorales.com.ar / https://ai.dmorales.site)
       │
       ▼
[Cloudflare Tunnel / FastAPI Gateway (Puerto 8000)]
       │
       ├──► 🧠 Antigravity Agent Runtime (Orchestrator v1.5.2)
       │     ├── Inferencia Local: Ollama (qwen2.5:1.5b) / Cloud: Gemini Free Tier (15 RPM / 1M tokens)
       │     ├── SafeTextualToolParser: Dispatch de herramientas con control de tipos y argumentos
       │     ├── PermissionsEngine: Seguridad estricta (READ_ONLY / APPROVAL_REQUIRED / AUTONOMOUS)
       │     └── Multi-Turn Loop: Re-inyección de resultados hasta 3 turnos para síntesis final
       │
       ├──► 🎨 Motor Creativo Multimodal (CreativeToolsEngine)
       │     ├── faceswap_image: Transferencia de identidad con preservación de outfit, pose y fondo
       │     ├── animate_image: Conversión de fotos en video MP4 cinematográfico
       │     ├── generate_image: Generación de arte e imágenes en alta resolución
       │     └── replicate_video: Réplica de movimiento desde video de referencia
       │
       ├──► 🔌 Google Drive 5 TB MCP Integration Layer (Costo $0)
       │     ├── gdrive_get_storage_quota: Monitoreo de los 5 TB de Google One
       │     ├── gdrive_list_files & gdrive_read_file: Exploración y lectura en la nube
       │     └── gdrive_search_files: Búsqueda rápida por palabras clave
       │
       └──► ⚡ GPU Worker Remoto (Google Colab Tesla T4 16 GB)
             ├── Bootstrap: deployment/colab_bootstrap.py
             ├── Modelos Pesados: FLUX.1 Schnell, Wan 2.1 Video, SDXL Juggernaut
             └── Almacenamiento Persistente: /content/drive/MyDrive (5 TB Google One)
```

---

## 2. 📂 Directorio de Archivos Críticos y Responsabilidades

| Componente | Ruta Física | Función Principal |
| :--- | :--- | :--- |
| **Orchestrator** | `src/integrations/antigravity/orchestrator.py` | Orquestador agéntico multi-motor y detector de intents. |
| **Tool Parser** | `src/integrations/antigravity/tool_parser.py` | Lista blanca de herramientas y parser de llamadas textuales. |
| **Creative Engine** | `src/integrations/antigravity/creative_tools.py` | Motor de FaceSwap, generación y video. |
| **Permissions** | `src/integrations/antigravity/permissions.py` | ACL y bloqueo de mutaciones no autorizadas en READ_ONLY. |
| **Google Drive MCP**| `src/mcp/gdrive_mcp.py` | Servidor MCP para Google One 5 TB a costo $0. |
| **Mobile Web PWA** | `src/api/mobile_web.py` | Interfaz táctil para iPhone con reproductor y descargas. |
| **API Gateway** | `src/api/server.py` | Servidor FastAPI con entrega de estáticos en `/api/generated`. |
| **Bootstrapper** | `start_platform.ps1` | Script de arranque como demonio local con túnel Cloudflare. |

---

## 3. 🛡️ Guía de Recuperación ante Cortes de Luz o Reinicio del PC

Si el PC se reinicia o se corta la luz, DM AI OS se recupera en **1 solo paso**:

```powershell
# En PowerShell (como Administrador o usuario normal):
cd C:\Users\moral\.gemini\antigravity-ide\scratch
powershell -ExecutionPolicy Bypass -File .\start_platform.ps1 -Daemon
```

**Lo que hace automáticamente:**
1. Conecta con Ollama local.
2. Inicia el API Gateway en el puerto `8000`.
3. Inicia el MCP Server en el puerto `8001`.
4. Levanta el túnel Cloudflare hacia `https://ai.dmorales.site` y `https://ai.dmorales.com.ar`.
5. Deja el sistema listo para operar desde tu iPhone en menos de 10 segundos.

---

## 4. 🔒 Política de Invarianza

Cualquier futura extensión debe realizarse respetando:
* **Cero regresiones:** No modificar las firmas ni el funcionamiento de `faceswap_image`, `gdrive_mcp` ni `PermissionsEngine`.
* **Modo Seguro:** El modo por defecto de Antigravity sigue siendo `READ_ONLY` con SHA256 inviolable en el workspace.
