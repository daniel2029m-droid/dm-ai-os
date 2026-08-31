# ⚙️ DM AI OS v1.5.2 — Antigravity Runtime Specification

## 1. Especificación del Runtime

* **Paquete:** `google-antigravity==0.1.15` (Wheel oficial x86_64).
* **Arnés de Ejecución:** `localharness.exe` (subproceso local con loopback WebSocket `ws://127.0.0.1:<puerto>/`).
* **Estrategia de Conexión:** `LocalOpenAIConnectionStrategy` / `LocalOpenAIAgentConfig`.
* **Inferencia Local:** Ollama (`127.0.0.1:11434/v1`) con modelo `qwen2.5:1.5b`.
* **Workspace Físico:** `C:\Users\moral\.gemini\antigravity-ide\scratch`.

## 2. Herramientas Físicas Conectadas al Runtime

* `list_workspace_directory(subpath: str)`: Escaneo y enumeración real del filesystem.
* `read_workspace_file(file_path: str)`: Inspección física de archivos en UTF-8.
* `write_to_file` / `replace_file_content`: Mutaciones bajo control interactivo.
