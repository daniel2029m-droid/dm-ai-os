# 🚀 Guía de Integración: Google One 5 TB & Gemini Free Tier a Costo $0

Esta guía detalla cómo aprovechar al máximo tu suscripción **Google One (5 TB)** y los modelos de IA de Google en **DM AI OS** y **Antigravity** sin costos adicionales de API ni servidores cloud pagos.

---

## 1. 🧠 Gemini 2.5 Flash / Pro a Costo $0 (Google AI Studio)

Google ofrece una capa **100% gratuita** para desarrolladores a través de **Google AI Studio**:

### Pasos para obtener tu clave gratuita:
1. Ingresa a [https://aistudio.google.com](https://aistudio.google.com) con tu cuenta de Google One.
2. Haz clic en **"Get API Key"** (Obtener clave de API).
3. Selecciona **"Create API Key in new project"**.
4. Copia la clave generada y agrégala en tu archivo `.env` en DM AI OS:
   ```env
   GEMINI_API_KEY="AIzaSy..."
   ```

### Beneficios incluidos a $0:
* **Hasta 15 peticiones por minuto (RPM)** y **1.000.000 de tokens por día** totalmente gratis.
* Máxima fidelidad en llamadas a herramientas (`function calling`) y razonamiento agéntico avanzado sin alucinaciones.

---

## 2. 🔌 Google Drive 5 TB vía MCP (Model Context Protocol)

DM AI OS v1.5.2 incluye el conector **`GoogleDriveMCP`** (`src/mcp/gdrive_mcp.py`), que expone las siguientes herramientas seguras:

| Herramienta MCP | Descripción | Permisos |
| :--- | :--- | :--- |
| `gdrive_get_storage_quota` | Consulta capacidad (5 TB), estado de montaje y cuota disponible. | READ_ONLY |
| `gdrive_list_files` | Lista carpetas y archivos en la nube de Google Drive. | READ_ONLY |
| `gdrive_read_file` | Lee documentos, prompts y archivos de configuración en Drive. | READ_ONLY |
| `gdrive_search_files` | Busca archivos por palabra clave en todo el Drive. | READ_ONLY |

---

## 3. 🎨 Persistencia de Checkpoints y Renders en Google Colab

Para la generación de imágenes y videos en alta resolución (FLUX, Wan 2.1, LTX-Video) sin saturar el almacenamiento local:

1. Inicia el worker de Google Colab ejecutando el bootstrap:
   ```python
   # En Google Colab con GPU Tesla T4:
   from google.colab import drive
   drive.mount('/content/drive')
   !python deployment/colab_bootstrap.py
   ```
2. Los modelos pesados (10-25 GB) y los renders generados se guardan automáticamente en tu Google One de 5 TB en:
   - `/content/drive/MyDrive/DM-AI-OS-MODELS`
   - `/content/drive/MyDrive/DM_AI_OS`
3. **Costo de almacenamiento y transferencia:** **$0.00**.
